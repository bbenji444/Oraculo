"""``EntityRepositoryPort`` sobre PostgreSQL (Fases 9.4 y 9.5; migraciones 0018 a 0022).

Guarda lo que la IA leyó de cada nota (``entity_extractions``) y lo convierte
en sugerencias de un caso (``entities``, ``entity_aliases``,
``entity_mentions`` y ``case_entities``). Desde la 9.5 también sugiere, une y
separa entidades del caso.

- **Agrupar dentro del caso (decisión D6 de la 9.4):** una propuesta se suma a
  la sugerencia del MISMO caso con el mismo tipo y nombre de comparación
  (``entity_name_norm``). Nunca se junta con una de otro caso ni con una ya
  confirmada o descartada (ADR-0104): si la que existe ya se revisó, nace otra
  sugerencia, que se ofrece para unir.
- **Una nota por caso a la vez:** ``materialize``, unir y separar toman un
  candado de la base por caso (``pg_advisory_xact_lock``), para que dos notas
  con la misma persona leídas al mismo tiempo no creen dos sugerencias ni se
  una algo mientras el worker le suma menciones.
- **Sin duplicar evidencia:** si la nota se quitó y se volvió a agregar, sus
  menciones ya están en el caso y no se repiten, aunque su entidad se haya
  unido a otra o separado desde entonces.
- **Grupos de fusión (9.5, D4):** unir solo escribe ``merged_into``. Las
  lecturas resuelven cada entidad raíz con las que se le unieron
  (``_GROUPS_CTE``) y muestran sus menciones y alias juntos; separar es
  borrar ese ``merged_into``.
- **Sugerencias de fusión (9.5, D2 y D3):** se calculan al leer
  (``_MERGE_SUGGESTIONS_SQL``); solo se guarda el «No son la misma».
- **Lo que se ve:** una sugerencia cuyas menciones son todas de notas que ya
  no están en el caso no aparece (vuelve si la nota regresa); lo ya revisado
  siempre aparece, porque lo decidió una persona.

Cada escritura que cambia el caso guarda su registro en ``audit_log`` en la
misma transacción.

No hace: no revisa lo que propuso la IA ni decide permisos (dominio y casos de
uso); nunca toca la tabla reservada de enlaces externos (ADR-0101).
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.adapters.persistence.article_rows import place_name
from app.adapters.persistence.cases_repository import touch, write_audit
from app.application.audit import AuditEntry
from app.application.ports.entities import (
    ArticleSource,
    CaseAnalysis,
    CaseEntity,
    FailedExtraction,
    Materialized,
    MentionView,
    MergedEntity,
    MergeSuggestion,
    StoredExtraction,
)
from app.domain.enrichment import LLMUsage
from app.domain.entity_extraction import (
    CaseArticleEntitiesStatus,
    Proposal,
    Rejection,
    RejectionReason,
    ReviewedProposals,
    TextSource,
    match_region,
)
from app.domain.entity_resolution import (
    TRIGRAM_MERGE_THRESHOLD,
    MergeCandidate,
    MergeReason,
    entity_name_norm,
)
from app.domain.errors import EntityMergeError, EntityNotFoundError
from app.domain.extraction import ExtractionStatus
from app.domain.geocoding import MentionRole
from app.domain.investigation import EntityType, LegalStatus, ReviewStatus

# Primer número del candado de la base (pg_advisory_xact_lock(int, int)):
# separa estos candados de cualquier otro que use el sistema. 904 = fase 9.4.
_LOCK_NAMESPACE = 904

_ENTITY_COLUMNS = """
    e.id, e.type, e.canonical_label, e.review_status, e.legal_status, e.reviewed_by,
    e.reviewed_at, e.region_id, r.level::text AS region_level, r.display_prefix,
    r.name AS region_name
"""
# Grupos de fusión del caso (9.5, decisión D4): cada entidad raíz (no unida a
# otra) con las que se le unieron, directo o en cadena. Las filas unidas no
# cambian al fusionar: las lecturas las resuelven aquí, y separar es solo
# borrar su ``merged_into``. Va acotado al caso: solo se une dentro de uno.
_GROUPS_CTE = """
    WITH RECURSIVE grp(root, id) AS (
        SELECT e.id, e.id FROM case_entities ce JOIN entities e ON e.id = ce.entity_id
        WHERE ce.case_id = :case AND e.merged_into IS NULL
        UNION ALL
        SELECT grp.root, c.id FROM grp JOIN entities c ON c.merged_into = grp.id
    )
"""
# Una sugerencia se ve solo si su grupo tiene al menos una mención en una nota
# que sigue en el caso; lo revisado siempre se ve.
_VISIBLE = """
    (e.review_status <> 'suggested' OR EXISTS (
        SELECT 1 FROM grp JOIN entity_mentions m ON m.entity_id = grp.id
        JOIN case_articles ca ON ca.case_id = ce.case_id AND ca.article_id = m.article_id
        WHERE grp.root = e.id))
"""


_ENTITIES_OF_CASE = f"""
    {_GROUPS_CTE}
    SELECT {_ENTITY_COLUMNS}
    FROM case_entities ce
    JOIN entities e ON e.id = ce.entity_id
    LEFT JOIN regions r ON r.id = e.region_id
    WHERE ce.case_id = :case AND e.merged_into IS NULL
"""  # noqa: S608 — columnas fijas de este módulo; los datos van por parámetro
_LIST_SQL = f"""
    {_ENTITIES_OF_CASE} AND e.review_status = :status AND {_VISIBLE}
"""
_ONE_SQL = f"""
    {_ENTITIES_OF_CASE} AND e.id = :entity
"""
_COUNTS_SQL = f"""
    {_GROUPS_CTE}
    SELECT e.review_status, count(*)
    FROM case_entities ce
    JOIN entities e ON e.id = ce.entity_id
    WHERE ce.case_id = :case AND e.merged_into IS NULL AND {_VISIBLE}
    GROUP BY e.review_status
"""  # noqa: S608 — condiciones fijas de este módulo; los datos van por parámetro
# Sugerencias de fusión (D2): pares de raíces visibles, no descartadas y del
# mismo tipo con el mismo nombre, un nombre o alias en común (contando los de
# todo el grupo) o nombres parecidos. El parecido usa el operador % de
# pg_trgm (umbral fijado con set_config en la misma transacción) para que
# entre el índice GIN entities_label_trgm. Se quitan los pares que alguien
# descartó, aunque el descarte se haya hecho sobre otro miembro del grupo.
_MERGE_SUGGESTIONS_SQL = f"""
    {_GROUPS_CTE},
    roots AS (
        SELECT e.id, e.type, e.label_norm FROM case_entities ce
        JOIN entities e ON e.id = ce.entity_id
        WHERE ce.case_id = :case AND e.merged_into IS NULL
          AND e.review_status <> 'discarded' AND {_VISIBLE}
    ),
    names AS (
        SELECT grp.root, e.label_norm AS name FROM grp JOIN entities e ON e.id = grp.id
        UNION
        SELECT grp.root, a.alias_norm FROM grp JOIN entity_aliases a ON a.entity_id = grp.id
    ),
    candidates AS (
        SELECT a.id AS first, b.id AS second, 'same_name' AS reason
        FROM roots a JOIN roots b
          ON b.type = a.type AND b.id > a.id AND b.label_norm = a.label_norm
        UNION ALL
        SELECT DISTINCT a.id, b.id, 'shared_name'
        FROM roots a
        JOIN names na ON na.root = a.id
        JOIN names nb ON nb.name = na.name AND nb.root > a.id
        JOIN roots b ON b.id = nb.root AND b.type = a.type
        UNION ALL
        SELECT a.id, b.id, 'similar_name'
        FROM roots a
        JOIN entities b ON b.label_norm % a.label_norm AND b.type = a.type AND b.id > a.id
        JOIN roots rb ON rb.id = b.id
    ),
    dismissed AS (
        SELECT least(g1.root, g2.root) AS first, greatest(g1.root, g2.root) AS second
        FROM entity_merge_dismissals d
        JOIN grp g1 ON g1.id = d.entity_low
        JOIN grp g2 ON g2.id = d.entity_high
        WHERE d.case_id = :case
    )
    SELECT c.first, c.second, array_agg(DISTINCT c.reason) AS reasons
    FROM candidates c
    WHERE NOT EXISTS (
        SELECT 1 FROM dismissed x WHERE x.first = c.first AND x.second = c.second)
    GROUP BY c.first, c.second
"""  # noqa: S608 — consultas fijas de este módulo; los datos van por parámetro


def _lock_key(case_id: UUID) -> int:
    """Los primeros 4 bytes del caso como entero de 32 bits con signo (lo que pide la función)."""
    return int.from_bytes(case_id.bytes[:4], "big", signed=True)


def _reviewed_json(reviewed: ReviewedProposals) -> str:
    return json.dumps(
        {
            "entities": [
                {
                    "type": p.type.value,
                    "label": p.label,
                    "label_norm": p.label_norm,
                    "aliases": list(p.aliases),
                    "role": p.role.value,
                    "legal_status_hint": p.legal_status_hint.value if p.legal_status_hint else None,
                    "confidence": p.confidence,
                    "evidence_span": p.evidence_span,
                    "char_start": p.char_start,
                    "char_end": p.char_end,
                }
                for p in reviewed.proposals
            ],
            "rejected": [
                {
                    "type": r.type,
                    "label": r.label,
                    "reason": r.reason.value,
                    "evidence_span": r.evidence_span,
                }
                for r in reviewed.rejected
            ],
        },
        ensure_ascii=False,
    )


def _reviewed_from(data: Mapping[str, Any]) -> ReviewedProposals:
    return ReviewedProposals(
        proposals=tuple(
            Proposal(
                type=EntityType(p["type"]),
                label=p["label"],
                # Se recalcula: las lecturas de la 9.4 lo guardaron con comillas.
                label_norm=entity_name_norm(p["label"]),
                aliases=tuple(p["aliases"]),
                role=MentionRole(p["role"]),
                legal_status_hint=(
                    LegalStatus(p["legal_status_hint"]) if p["legal_status_hint"] else None
                ),
                confidence=float(p["confidence"]),
                evidence_span=p["evidence_span"],
                char_start=p["char_start"],
                char_end=p["char_end"],
            )
            for p in data.get("entities", [])
        ),
        rejected=tuple(
            Rejection(r["type"], r["label"], RejectionReason(r["reason"]), r["evidence_span"])
            for r in data.get("rejected", [])
        ),
    )


def _mention(row: RowMapping) -> MentionView:
    return MentionView(
        mention_id=row["id"],
        entity_id=row["entity_id"],
        article_id=row["article_id"],
        article_title=row["title"],
        article_url=row["url_canonical"],
        source_name=row["source_name"] or row["source_domain"],
        published_at=row["published_at"],
        mention_text=row["mention_text"],
        role=MentionRole(row["role"]),
        legal_status_hint=(
            LegalStatus(row["legal_status_hint"]) if row["legal_status_hint"] else None
        ),
        confidence=float(row["confidence"]),
        evidence_span=row["evidence_span"],
    )


class PostgresEntityRepository:
    """Entidades de los casos y lo que la IA leyó de cada nota."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe la conexión compartida.

        Args:
            engine: Motor asíncrono de SQLAlchemy.
        """
        self._engine = engine

    async def article_source(self, case_id: UUID, article_id: int) -> ArticleSource | None:
        """Ver ``EntityRepositoryPort.article_source``."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT ca.entities_status, a.title, a.snippet, a.extraction_status, "
                            "a.published_at, t.body FROM case_articles ca "
                            "JOIN articles a ON a.id = ca.article_id "
                            "LEFT JOIN article_texts t ON t.article_id = a.id "
                            "WHERE ca.case_id = :case AND ca.article_id = :article"
                        ),
                        {"case": case_id, "article": article_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return ArticleSource(
            article_id=article_id,
            status=CaseArticleEntitiesStatus(row["entities_status"]),
            title=row["title"],
            snippet=row["snippet"],
            stored_body=row["body"],
            full_text=row["extraction_status"] == ExtractionStatus.OK,
            published_at=row["published_at"],
        )

    async def done_count(self, case_id: UUID) -> int:
        """Ver ``EntityRepositoryPort.done_count``."""
        async with self._engine.connect() as conn:
            count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM case_articles "
                        "WHERE case_id = :case AND entities_status = 'done'"
                    ),
                    {"case": case_id},
                )
            ).scalar_one()
        return int(count)

    async def get_extraction(self, article_id: int, prompt_version: str) -> StoredExtraction | None:
        """Ver ``EntityRepositoryPort.get_extraction``."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT model, source, output, tokens_in, tokens_out, cost_usd "
                            "FROM entity_extractions WHERE article_id = :article "
                            "AND prompt_version = :version AND status = 'ok'"
                        ),
                        {"article": article_id, "version": prompt_version},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return StoredExtraction(
            article_id=article_id,
            prompt_version=prompt_version,
            model=row["model"],
            source=TextSource(row["source"]),
            reviewed=_reviewed_from(row["output"]),
            usage=LLMUsage(row["tokens_in"], row["tokens_out"]),
            cost_usd=float(row["cost_usd"]),
        )

    async def save_extraction(self, extraction: StoredExtraction) -> None:
        """Ver ``EntityRepositoryPort.save_extraction``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO entity_extractions (article_id, prompt_version, status, model, "
                    "source, output, rejected_count, tokens_in, tokens_out, cost_usd) "
                    "VALUES (:article, :version, 'ok', :model, :source, CAST(:output AS jsonb), "
                    ":rejected, :tin, :tout, :cost) "
                    "ON CONFLICT (article_id, prompt_version) DO UPDATE SET status = 'ok', "
                    "model = EXCLUDED.model, source = EXCLUDED.source, output = EXCLUDED.output, "
                    "rejected_count = EXCLUDED.rejected_count, "
                    # Los intentos fallidos anteriores también se cobraron.
                    "tokens_in = entity_extractions.tokens_in + EXCLUDED.tokens_in, "
                    "tokens_out = entity_extractions.tokens_out + EXCLUDED.tokens_out, "
                    "cost_usd = entity_extractions.cost_usd + EXCLUDED.cost_usd, "
                    "error = NULL, updated_at = now()"
                ),
                {
                    "article": extraction.article_id,
                    "version": extraction.prompt_version,
                    "model": extraction.model,
                    "source": extraction.source.value,
                    "output": _reviewed_json(extraction.reviewed),
                    "rejected": len(extraction.reviewed.rejected),
                    "tin": extraction.usage.tokens_in,
                    "tout": extraction.usage.tokens_out,
                    "cost": extraction.cost_usd,
                },
            )

    async def save_failure(
        self, case_id: UUID, failure: FailedExtraction, audit: AuditEntry
    ) -> None:
        """Ver ``EntityRepositoryPort.save_failure``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO entity_extractions (article_id, prompt_version, status, model, "
                    "source, tokens_in, tokens_out, cost_usd, error) "
                    "VALUES (:article, :version, 'failed', :model, :source, :tin, :tout, :cost, "
                    ":error) "
                    # Si otra lectura ya salió bien, se conserva; solo se suma lo gastado.
                    "ON CONFLICT (article_id, prompt_version) DO UPDATE SET "
                    "tokens_in = entity_extractions.tokens_in + EXCLUDED.tokens_in, "
                    "tokens_out = entity_extractions.tokens_out + EXCLUDED.tokens_out, "
                    "cost_usd = entity_extractions.cost_usd + EXCLUDED.cost_usd, "
                    "error = EXCLUDED.error, updated_at = now()"
                ),
                {
                    "article": failure.article_id,
                    "version": failure.prompt_version,
                    "model": failure.model,
                    "source": failure.source.value,
                    "tin": failure.usage.tokens_in,
                    "tout": failure.usage.tokens_out,
                    "cost": failure.cost_usd,
                    "error": failure.error,
                },
            )
            await conn.execute(
                text(
                    "UPDATE case_articles SET entities_status = 'failed', "
                    "entities_cost_usd = entities_cost_usd + :cost "
                    "WHERE case_id = :case AND article_id = :article"
                ),
                {"case": case_id, "article": failure.article_id, "cost": failure.cost_usd},
            )
            await write_audit(conn, case_id, audit)

    async def materialize(
        self, case_id: UUID, extraction: StoredExtraction, cost_usd: float, audit: AuditEntry
    ) -> Materialized | None:
        """Ver ``EntityRepositoryPort.materialize``."""
        article_id = extraction.article_id
        async with self._engine.begin() as conn:
            await self._lock(conn, case_id)
            in_case = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM case_articles WHERE case_id = :case "
                        "AND article_id = :article FOR UPDATE"
                    ),
                    {"case": case_id, "article": article_id},
                )
            ).first()
            if in_case is None:
                return None
            locations = [
                (row[0], row[1])
                for row in await conn.execute(
                    text(
                        "SELECT mention_text, region_id FROM article_locations "
                        "WHERE article_id = :article ORDER BY is_primary DESC, id"
                    ),
                    {"article": article_id},
                )
            ]
            counts = {"created": 0, "attached": 0, "skipped": 0}
            for proposal in extraction.reviewed.proposals:
                outcome = await self._save_proposal(
                    conn,
                    case_id=case_id,
                    extraction=extraction,
                    proposal=proposal,
                    locations=locations,
                    added_by=audit.actor.user_id,
                )
                counts[outcome] += 1
            await conn.execute(
                text(
                    "UPDATE case_articles SET entities_status = 'done', "
                    "entities_cost_usd = entities_cost_usd + :cost "
                    "WHERE case_id = :case AND article_id = :article"
                ),
                {"case": case_id, "article": article_id, "cost": cost_usd},
            )
            await write_audit(
                conn, case_id, AuditEntry(audit.actor, audit.action, {**audit.payload, **counts})
            )
        return Materialized(**counts)

    async def _save_proposal(  # noqa: PLR0913 — la propuesta con su nota, su caso y quién
        self,
        conn: AsyncConnection,
        *,
        case_id: UUID,
        extraction: StoredExtraction,
        proposal: Proposal,
        locations: Sequence[tuple[str, int | None]],
        added_by: str,
    ) -> str:
        """Suma una propuesta al caso. Devuelve ``created``, ``attached`` o ``skipped``."""
        article_id = extraction.article_id
        # La mención ya está en el caso (la nota se quitó y se volvió a agregar)
        # aunque desde entonces su entidad se haya unido a otra o se haya
        # separado con otro nombre (9.5): se busca por la mención, no por el
        # nombre de la entidad.
        already = (
            await conn.execute(
                text(
                    "SELECT 1 FROM entity_mentions m "
                    "JOIN case_entities ce ON ce.entity_id = m.entity_id AND ce.case_id = :case "
                    "JOIN entities e ON e.id = m.entity_id AND e.type = :type "
                    "WHERE m.article_id = :article AND m.evidence_span = :evidence "
                    "AND m.mention_text = :mention LIMIT 1"
                ),
                {
                    "case": case_id,
                    "type": proposal.type.value,
                    "article": article_id,
                    "evidence": proposal.evidence_span,
                    "mention": proposal.label,
                },
            )
        ).first()
        if already is not None:
            return "skipped"
        same_name = (
            (
                await conn.execute(
                    text(
                        "SELECT e.id, e.review_status "
                        "FROM case_entities ce JOIN entities e ON e.id = ce.entity_id "
                        "WHERE ce.case_id = :case AND e.type = :type AND e.label_norm = :norm "
                        "AND e.merged_into IS NULL ORDER BY e.id"
                    ),
                    {"case": case_id, "type": proposal.type.value, "norm": proposal.label_norm},
                )
            )
            .mappings()
            .all()
        )
        region_id = (
            match_region(
                [proposal.label_norm, *(entity_name_norm(a) for a in proposal.aliases)], locations
            )
            if proposal.type is EntityType.PLACE
            else None
        )
        target = next((r["id"] for r in same_name if r["review_status"] == "suggested"), None)
        outcome = "attached"
        if target is None:
            outcome = "created"
            target = (
                await conn.execute(
                    text(
                        "INSERT INTO entities (type, canonical_label, label_norm, region_id) "
                        "VALUES (:type, :label, :norm, :region) RETURNING id"
                    ),
                    {
                        "type": proposal.type.value,
                        "label": proposal.label,
                        "norm": proposal.label_norm,
                        "region": region_id,
                    },
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO case_entities (case_id, entity_id, added_by) "
                    "VALUES (:case, :entity, :by)"
                ),
                {"case": case_id, "entity": target, "by": added_by},
            )
        elif region_id is not None:
            await conn.execute(
                text(
                    "UPDATE entities SET region_id = :region, updated_at = now() "
                    "WHERE id = :entity AND region_id IS NULL"
                ),
                {"entity": target, "region": region_id},
            )
        for alias in proposal.aliases:
            await conn.execute(
                text(
                    "INSERT INTO entity_aliases (entity_id, alias, alias_norm) "
                    "VALUES (:entity, :alias, :norm) ON CONFLICT (entity_id, alias_norm) DO NOTHING"
                ),
                {"entity": target, "alias": alias, "norm": entity_name_norm(alias)},
            )
        await conn.execute(
            text(
                "INSERT INTO entity_mentions (entity_id, article_id, mention_text, role, "
                "legal_status_hint, confidence, evidence_span, char_start, char_end, "
                "extracted_by, prompt_version) VALUES (:entity, :article, :mention, :role, "
                ":hint, :confidence, :evidence, :start, :end, :model, :version) "
                "ON CONFLICT (entity_id, article_id, evidence_span) DO NOTHING"
            ),
            {
                "entity": target,
                "article": article_id,
                "mention": proposal.label,
                "role": proposal.role.value,
                "hint": proposal.legal_status_hint.value if proposal.legal_status_hint else None,
                "confidence": proposal.confidence,
                "evidence": proposal.evidence_span,
                "start": proposal.char_start,
                "end": proposal.char_end,
                "model": extraction.model,
                "version": extraction.prompt_version,
            },
        )
        return outcome

    async def set_status(
        self, case_id: UUID, article_ids: Sequence[int], status: CaseArticleEntitiesStatus
    ) -> None:
        """Ver ``EntityRepositoryPort.set_status``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE case_articles SET entities_status = :status "
                    "WHERE case_id = :case AND article_id = ANY(:ids) "
                    # Lo ya leído no vuelve atrás (una pestaña vieja o un doble clic).
                    "AND entities_status <> 'done'"
                ),
                {"status": status.value, "case": case_id, "ids": list(article_ids)},
            )

    async def to_analyze(self, case_id: UUID, limit: int) -> list[int]:
        """Ver ``EntityRepositoryPort.to_analyze``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT article_id FROM case_articles WHERE case_id = :case "
                    "AND entities_status IN ('pending', 'failed') "
                    "ORDER BY created_at, article_id LIMIT :limit"
                ),
                {"case": case_id, "limit": limit},
            )
            return [int(row[0]) for row in rows]

    async def analysis(self, case_id: UUID) -> CaseAnalysis:
        """Ver ``EntityRepositoryPort.analysis``."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT count(*) AS articles, "
                            "count(*) FILTER (WHERE entities_status = 'pending') AS pending, "
                            "count(*) FILTER (WHERE entities_status = 'queued') AS queued, "
                            "count(*) FILTER (WHERE entities_status = 'done') AS done, "
                            "count(*) FILTER (WHERE entities_status = 'failed') AS failed, "
                            "count(*) FILTER (WHERE entities_status = 'skipped') AS skipped, "
                            "count(*) FILTER (WHERE entities_status = 'done' AND EXISTS ("
                            "SELECT 1 FROM entity_extractions x WHERE x.article_id = "
                            "ca.article_id AND x.status = 'ok' AND x.source = 'title_snippet'"
                            ")) AS title_snippet, "
                            "COALESCE(sum(entities_cost_usd), 0) AS cost "
                            "FROM case_articles ca WHERE case_id = :case"
                        ),
                        {"case": case_id},
                    )
                )
                .mappings()
                .one()
            )
        return CaseAnalysis(
            articles=int(row["articles"]),
            pending=int(row["pending"]),
            queued=int(row["queued"]),
            done=int(row["done"]),
            failed=int(row["failed"]),
            skipped=int(row["skipped"]),
            title_snippet=int(row["title_snippet"]),
            cost_usd=float(row["cost"]),
        )

    async def list_entities(self, case_id: UUID, status: ReviewStatus) -> list[CaseEntity]:
        """Ver ``EntityRepositoryPort.list_entities``."""
        async with self._engine.connect() as conn:
            rows = (
                (await conn.execute(text(_LIST_SQL), {"case": case_id, "status": status.value}))
                .mappings()
                .all()
            )
            return await self._with_details(conn, case_id, rows)

    async def review_counts(self, case_id: UUID) -> dict[ReviewStatus, int]:
        """Ver ``EntityRepositoryPort.review_counts``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(text(_COUNTS_SQL), {"case": case_id})
            found = {ReviewStatus(row[0]): int(row[1]) for row in rows}
        return {status: found.get(status, 0) for status in ReviewStatus}

    async def get_entity(self, case_id: UUID, entity_id: int) -> CaseEntity | None:
        """Ver ``EntityRepositoryPort.get_entity``."""
        async with self._engine.connect() as conn:
            return await self._entity(conn, case_id, entity_id)

    async def review(  # noqa: PLR0913 — cada dato de la revisión firmada, por nombre (*)
        self,
        case_id: UUID,
        entity_id: int,
        *,
        status: ReviewStatus,
        legal_status: LegalStatus | None,
        reviewer: str,
        audit: AuditEntry,
    ) -> CaseEntity:
        """Ver ``EntityRepositoryPort.review``."""
        async with self._engine.begin() as conn:
            changed = (
                await conn.execute(
                    text(
                        "UPDATE entities SET review_status = :status, legal_status = :legal, "
                        "reviewed_by = :by, reviewed_at = now(), updated_at = now() "
                        "WHERE id = :entity AND id IN "
                        "(SELECT entity_id FROM case_entities WHERE case_id = :case) "
                        "RETURNING id"
                    ),
                    {
                        "status": status.value,
                        "legal": legal_status.value if legal_status else None,
                        "by": reviewer,
                        "entity": entity_id,
                        "case": case_id,
                    },
                )
            ).first()
            if changed is None:
                raise EntityNotFoundError(
                    "No existe esa entidad en el caso.",
                    {"case_id": str(case_id), "entity_id": entity_id},
                )
            await write_audit(conn, case_id, audit)
            await touch(conn, case_id)
            entity = await self._entity(conn, case_id, entity_id)
        if entity is None:
            raise EntityNotFoundError("No existe esa entidad en el caso.", {"entity_id": entity_id})
        return entity

    async def merge_suggestions(self, case_id: UUID) -> list[MergeSuggestion]:
        """Ver ``EntityRepositoryPort.merge_suggestions``."""
        # begin() y no connect(): set_config(..., true) vale solo dentro de la
        # transacción, y así no se queda puesto en la conexión del pool.
        async with self._engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('pg_trgm.similarity_threshold', :threshold, true)"),
                {"threshold": str(TRIGRAM_MERGE_THRESHOLD)},
            )
            pairs = (
                (await conn.execute(text(_MERGE_SUGGESTIONS_SQL), {"case": case_id}))
                .mappings()
                .all()
            )
            if not pairs:
                return []
            ids = sorted({row["first"] for row in pairs} | {row["second"] for row in pairs})
            rows = (
                (
                    await conn.execute(
                        text(f"{_ENTITIES_OF_CASE} AND e.id = ANY(:ids)"),
                        {"case": case_id, "ids": ids},
                    )
                )
                .mappings()
                .all()
            )
            by_id = {e.entity_id: e for e in await self._with_details(conn, case_id, rows)}
        return [
            MergeSuggestion(
                by_id[row["first"]],
                by_id[row["second"]],
                frozenset(MergeReason(reason) for reason in row["reasons"]),
            )
            for row in pairs
        ]

    async def merge_candidate(self, case_id: UUID, entity_id: int) -> MergeCandidate | None:
        """Ver ``EntityRepositoryPort.merge_candidate``."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT e.id, e.type, e.review_status, e.merged_into "
                            "FROM case_entities ce JOIN entities e ON e.id = ce.entity_id "
                            "WHERE ce.case_id = :case AND e.id = :entity"
                        ),
                        {"case": case_id, "entity": entity_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return MergeCandidate(
            row["id"],
            EntityType(row["type"]),
            ReviewStatus(row["review_status"]),
            row["merged_into"],
        )

    async def merge(
        self, case_id: UUID, keep_id: int, merge_id: int, audit: AuditEntry
    ) -> CaseEntity:
        """Ver ``EntityRepositoryPort.merge``."""
        async with self._engine.begin() as conn:
            await self._lock(conn, case_id)
            # Se vuelve a exigir lo que validó el caso de uso, por si otra
            # persona unió o descartó alguna en el inter.
            changed = (
                await conn.execute(
                    text(
                        "UPDATE entities SET merged_into = :keep, updated_at = now() "
                        "WHERE id = :merge AND merged_into IS NULL "
                        "AND review_status <> 'discarded' AND id IN ("
                        "SELECT entity_id FROM case_entities WHERE case_id = :case) "
                        "AND EXISTS (SELECT 1 FROM entities k "
                        "JOIN case_entities ck ON ck.entity_id = k.id AND ck.case_id = :case "
                        "WHERE k.id = :keep AND k.merged_into IS NULL "
                        "AND k.review_status <> 'discarded') RETURNING id"
                    ),
                    {"keep": keep_id, "merge": merge_id, "case": case_id},
                )
            ).first()
            if changed is None:
                raise EntityMergeError(
                    "Una de las dos entidades cambió mientras tanto; vuelve a cargar el caso.",
                    {"keep_id": keep_id, "merge_id": merge_id},
                )
            await write_audit(conn, case_id, audit)
            await touch(conn, case_id)
            kept = await self._entity(conn, case_id, keep_id)
        if kept is None:
            raise EntityNotFoundError("No existe esa entidad en el caso.", {"entity_id": keep_id})
        return kept

    async def unmerge(self, case_id: UUID, entity_id: int, audit: AuditEntry) -> CaseEntity:
        """Ver ``EntityRepositoryPort.unmerge``."""
        async with self._engine.begin() as conn:
            await self._lock(conn, case_id)
            changed = (
                await conn.execute(
                    text(
                        "UPDATE entities SET merged_into = NULL, updated_at = now() "
                        "WHERE id = :entity AND merged_into IS NOT NULL AND id IN ("
                        "SELECT entity_id FROM case_entities WHERE case_id = :case) RETURNING id"
                    ),
                    {"entity": entity_id, "case": case_id},
                )
            ).first()
            if changed is None:
                raise EntityMergeError(
                    "Esa entidad no está unida a otra.", {"entity_id": entity_id}
                )
            await write_audit(conn, case_id, audit)
            await touch(conn, case_id)
            separated = await self._entity(conn, case_id, entity_id)
        if separated is None:
            raise EntityNotFoundError("No existe esa entidad en el caso.", {"entity_id": entity_id})
        return separated

    async def split(
        self, case_id: UUID, entity_id: int, mention_ids: Sequence[int], audit: AuditEntry
    ) -> CaseEntity:
        """Ver ``EntityRepositoryPort.split``."""
        ids = sorted(set(mention_ids))
        async with self._engine.begin() as conn:
            await self._lock(conn, case_id)
            source = (
                (
                    await conn.execute(
                        text(
                            "SELECT e.type, m.mention_text FROM entity_mentions m "
                            "JOIN entities e ON e.id = m.entity_id "
                            "JOIN case_entities ce ON ce.entity_id = e.id AND ce.case_id = :case "
                            "WHERE m.entity_id = :entity AND m.id = ANY(:ids) ORDER BY m.id LIMIT 1"
                        ),
                        {"case": case_id, "entity": entity_id, "ids": ids},
                    )
                )
                .mappings()
                .first()
            )
            if source is None:
                raise EntityMergeError(
                    "Esas menciones no son de esa entidad.", {"entity_id": entity_id}
                )
            label = source["mention_text"]
            new_id = (
                await conn.execute(
                    text(
                        "INSERT INTO entities (type, canonical_label, label_norm) "
                        "VALUES (:type, :label, :norm) RETURNING id"
                    ),
                    {"type": source["type"], "label": label, "norm": entity_name_norm(label)},
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO case_entities (case_id, entity_id, added_by) "
                    "VALUES (:case, :entity, :by)"
                ),
                {"case": case_id, "entity": new_id, "by": audit.actor.user_id},
            )
            moved = await conn.execute(
                text(
                    "UPDATE entity_mentions SET entity_id = :new "
                    "WHERE entity_id = :entity AND id = ANY(:ids)"
                ),
                {"new": new_id, "entity": entity_id, "ids": ids},
            )
            if moved.rowcount != len(ids):
                # Alguna ya no era de la entidad: se deshace todo (la transacción).
                raise EntityMergeError(
                    "Alguna de esas menciones ya no es de esa entidad; vuelve a cargar el caso.",
                    {"entity_id": entity_id},
                )
            await write_audit(
                conn,
                case_id,
                AuditEntry(audit.actor, audit.action, {**audit.payload, "new_entity_id": new_id}),
            )
            await touch(conn, case_id)
            created = await self._entity(conn, case_id, new_id)
        if created is None:
            raise EntityNotFoundError("No existe esa entidad en el caso.", {"entity_id": new_id})
        return created

    async def dismiss_merge(
        self, case_id: UUID, first_id: int, second_id: int, audit: AuditEntry
    ) -> bool:
        """Ver ``EntityRepositoryPort.dismiss_merge``."""
        async with self._engine.begin() as conn:
            saved = (
                await conn.execute(
                    text(
                        "INSERT INTO entity_merge_dismissals "
                        "(case_id, entity_low, entity_high, dismissed_by) "
                        "VALUES (:case, :low, :high, :by) ON CONFLICT DO NOTHING "
                        "RETURNING entity_low"
                    ),
                    {
                        "case": case_id,
                        "low": first_id,
                        "high": second_id,
                        "by": audit.actor.user_id,
                    },
                )
            ).first()
            if saved is None:
                return False
            await write_audit(conn, case_id, audit)
            await touch(conn, case_id)
        return True

    async def _lock(self, conn: AsyncConnection, case_id: UUID) -> None:
        """Candado del caso hasta que termine la transacción (el mismo de ``materialize``)."""
        await conn.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
            {"namespace": _LOCK_NAMESPACE, "key": _lock_key(case_id)},
        )

    async def _entity(
        self, conn: AsyncConnection, case_id: UUID, entity_id: int
    ) -> CaseEntity | None:
        rows = (
            (await conn.execute(text(_ONE_SQL), {"case": case_id, "entity": entity_id}))
            .mappings()
            .all()
        )
        found = await self._with_details(conn, case_id, rows)
        return found[0] if found else None

    async def _with_details(
        self, conn: AsyncConnection, case_id: UUID, rows: Sequence[RowMapping]
    ) -> list[CaseEntity]:
        """Agrega a cada entidad sus alias, sus menciones en notas del caso y su grupo.

        Lo de las entidades que se le unieron (9.5) se ve en ella: sus alias y
        sus menciones, que conservan el id de su dueña para poder separarlas.
        """
        ids = [row["id"] for row in rows]
        if not ids:
            return []
        root_of: dict[int, int] = {}
        merged: dict[int, list[MergedEntity]] = {}
        for root, member, label, merged_into in await conn.execute(
            text(
                "WITH RECURSIVE grp(root, id) AS ("
                "SELECT r, r FROM unnest(CAST(:ids AS bigint[])) AS r "
                "UNION ALL SELECT grp.root, c.id FROM grp "
                "JOIN entities c ON c.merged_into = grp.id) "
                "SELECT grp.root, e.id, e.canonical_label, e.merged_into FROM grp "
                "JOIN entities e ON e.id = grp.id ORDER BY e.id"
            ),
            {"ids": ids},
        ):
            root_of[member] = root
            if member != root:
                merged.setdefault(root, []).append(MergedEntity(member, label, merged_into))
        members = list(root_of)
        aliases: dict[int, list[str]] = {}
        for entity_id, alias in await conn.execute(
            text(
                "SELECT entity_id, alias FROM entity_aliases WHERE entity_id = ANY(:ids) "
                "ORDER BY id"
            ),
            {"ids": members},
        ):
            group_aliases = aliases.setdefault(root_of[entity_id], [])
            if alias not in group_aliases:
                group_aliases.append(alias)
        mentions: dict[int, list[MentionView]] = {}
        mention_rows = await conn.execute(
            text(
                "SELECT m.id, m.entity_id, m.article_id, a.title, a.url_canonical, "
                "a.source_name, a.source_domain, a.published_at, m.mention_text, m.role, "
                "m.legal_status_hint, m.confidence, m.evidence_span FROM entity_mentions m "
                "JOIN case_articles ca ON ca.article_id = m.article_id AND ca.case_id = :case "
                "JOIN articles a ON a.id = m.article_id WHERE m.entity_id = ANY(:ids) "
                "ORDER BY a.published_at DESC NULLS LAST, m.id DESC"
            ),
            {"case": case_id, "ids": members},
        )
        for row in mention_rows.mappings():
            mentions.setdefault(root_of[row["entity_id"]], []).append(_mention(row))
        return [
            CaseEntity(
                entity_id=row["id"],
                type=EntityType(row["type"]),
                label=row["canonical_label"],
                aliases=tuple(aliases.get(row["id"], [])),
                review_status=ReviewStatus(row["review_status"]),
                legal_status=LegalStatus(row["legal_status"]) if row["legal_status"] else None,
                reviewed_by=row["reviewed_by"],
                reviewed_at=row["reviewed_at"],
                region_id=row["region_id"],
                region_name=place_name(
                    row["region_level"], row["display_prefix"], row["region_name"]
                ),
                mentions=tuple(mentions.get(row["id"], [])),
                merged=tuple(merged.get(row["id"], [])),
            )
            for row in rows
        ]
