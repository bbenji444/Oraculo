"""``RelationshipRepositoryPort`` sobre PostgreSQL (Fase 9.5; migración 0018).

Junta dos fuentes de vínculos entre entidades **confirmadas** de un caso:

- **Coocurrencia, calculada al leer (D6):** dos entidades confirmadas que
  aparecen en la misma nota del caso forman «aparecen juntas». Se calcula con
  los grupos de fusión (``GROUPS_CTE``), así que unir o separar entidades, o
  quitar una nota, se refleja sin refrescar nada.
- **Guardados (``relationships``):** los que alguien revisó o dibujó. Si un
  calculado ya se revisó, gana lo guardado; si se descartó, no vuelve.

Cada entidad se muestra como la raíz de su grupo de fusión: un vínculo
guardado con una entidad que después se unió a otra se ve en la que quedó.

Cada escritura guarda su registro en ``audit_log`` en la misma transacción.

No hace: no decide permisos ni valida lo que escribe el analista; nunca toca
la tabla reservada de enlaces externos (ADR-0101).
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.adapters.persistence.cases_repository import touch, write_audit
from app.adapters.persistence.entities_repository import GROUPS_CTE
from app.application.audit import AuditEntry
from app.application.ports.relationships import (
    RelationshipEnd,
    RelationshipKey,
    RelationshipView,
    RelationshipWrite,
    SharedArticle,
)
from app.domain.investigation import (
    SYMMETRIC_RELATIONSHIPS,
    EntityType,
    LegalStatus,
    Origin,
    RelationshipType,
    ReviewStatus,
)
from app.domain.relationships import cooccurrence_confidence

# Cada entidad del caso con la raíz de su grupo de fusión.
_ROOTS_SQL = f"{GROUPS_CTE} SELECT grp.id, grp.root FROM grp"  # noqa: S608 — consulta fija
# En qué notas que siguen en el caso aparece cada grupo.
_PRESENCE_SQL = f"""
    {GROUPS_CTE}
    SELECT DISTINCT grp.root, m.article_id FROM grp
    JOIN entity_mentions m ON m.entity_id = grp.id
    JOIN case_articles ca ON ca.case_id = :case AND ca.article_id = m.article_id
"""  # noqa: S608 — consulta fija de este módulo; los datos van por parámetro
_CONFIRMED_SQL = """
    SELECT e.id, e.type, e.canonical_label, e.legal_status FROM case_entities ce
    JOIN entities e ON e.id = ce.entity_id
    WHERE ce.case_id = :case AND e.merged_into IS NULL AND e.review_status = 'confirmed'
"""
# Revisar uno guardado, o guardar uno nuevo (un calculado que alguien revisó
# o uno que dibujó una persona). La llave única es (entity_a, entity_b, type).
_UPDATE_SQL = """
    UPDATE relationships SET review_status = :status, reviewed_by = :by,
        reviewed_at = now(), custom_label = :label, confidence = :confidence,
        notes = COALESCE(:notes, notes), updated_at = now()
    WHERE id = :id
"""
_INSERT_SQL = """
    INSERT INTO relationships (entity_a, entity_b, type, custom_label, origin, confidence,
        review_status, reviewed_by, reviewed_at, notes)
    VALUES (:a, :b, :type, :label, :origin, :confidence, :status, :by, now(), :notes)
    ON CONFLICT (entity_a, entity_b, type) DO UPDATE SET
        review_status = EXCLUDED.review_status,
        reviewed_by = EXCLUDED.reviewed_by, reviewed_at = now(),
        custom_label = EXCLUDED.custom_label,
        confidence = EXCLUDED.confidence,
        notes = COALESCE(EXCLUDED.notes, relationships.notes),
        updated_at = now()
"""
# Las notas sin fecha van al final de la evidencia.
_UNDATED = datetime.min.replace(tzinfo=UTC)
# Si dos guardados caen en la misma llave al resolver fusiones, se muestra el
# que decidió una persona: confirmado antes que descartado antes que sugerido.
_REVIEW_PRIORITY = {
    ReviewStatus.CONFIRMED: 0,
    ReviewStatus.DISCARDED: 1,
    ReviewStatus.SUGGESTED: 2,
}


def _end(row: RowMapping) -> RelationshipEnd:
    return RelationshipEnd(
        entity_id=row["id"],
        type=EntityType(row["type"]),
        label=row["canonical_label"],
        legal_status=LegalStatus(row["legal_status"]) if row["legal_status"] else None,
    )


def _key(kind: RelationshipType, first: int, second: int) -> RelationshipKey:
    if kind in SYMMETRIC_RELATIONSHIPS:
        first, second = min(first, second), max(first, second)
    return RelationshipKey(first, second, kind)


class PostgresRelationshipRepository:
    """Vínculos de un caso: calculados por coocurrencia y guardados."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido de la aplicación.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def list_case(self, case_id: UUID) -> list[RelationshipView]:
        """Ver ``RelationshipRepositoryPort.list_case``."""
        async with self._engine.connect() as conn:
            ends = {
                row["id"]: _end(row)
                for row in (await conn.execute(text(_CONFIRMED_SQL), {"case": case_id})).mappings()
            }
            if len(ends) < 2:  # noqa: PLR2004 — un vínculo necesita dos entidades
                return []
            root_of = {
                int(member): int(root)
                for member, root in await conn.execute(text(_ROOTS_SQL), {"case": case_id})
            }
            articles_of: dict[int, set[int]] = defaultdict(set)
            for root, article in await conn.execute(text(_PRESENCE_SQL), {"case": case_id}):
                if root in ends:
                    articles_of[int(root)].add(int(article))
            stored = await self._stored(conn, root_of, ends)
            shared = self._shared(articles_of)
            article_rows = await self._articles(conn, {a for ids in shared.values() for a in ids})
        views: list[RelationshipView] = []
        for key, row in stored.items():
            evidence = shared.get((key.entity_a, key.entity_b)) or shared.get(
                (key.entity_b, key.entity_a), set()
            )
            origin = Origin(row["origin"])
            confidence = float(row["confidence"])
            if origin is Origin.COOCCURRENCE and evidence:
                confidence = cooccurrence_confidence(len(evidence))
            views.append(
                self._view(
                    key,
                    row=row,
                    ends=ends,
                    origin=origin,
                    confidence=confidence,
                    evidence=evidence,
                    articles=article_rows,
                )
            )
        for (first, second), evidence in shared.items():
            key = RelationshipKey(first, second, RelationshipType.APPEARS_WITH)
            if key in stored:
                continue
            views.append(
                RelationshipView(
                    relationship_id=None,
                    entity_a=ends[first],
                    entity_b=ends[second],
                    type=RelationshipType.APPEARS_WITH,
                    custom_label=None,
                    origin=Origin.COOCCURRENCE,
                    confidence=cooccurrence_confidence(len(evidence)),
                    review_status=ReviewStatus.SUGGESTED,
                    reviewed_by=None,
                    reviewed_at=None,
                    notes=None,
                    shared_articles=self._evidence(evidence, article_rows),
                )
            )
        return views

    async def save(self, case_id: UUID, write: RelationshipWrite, audit: AuditEntry) -> None:
        """Ver ``RelationshipRepositoryPort.save``."""
        await self.save_many(case_id, [(write, audit)])

    async def save_many(
        self, case_id: UUID, items: Sequence[tuple[RelationshipWrite, AuditEntry]]
    ) -> None:
        """Ver ``RelationshipRepositoryPort.save_many``."""
        # Una sola transacción: si una falla, ``begin`` deshace todas (ADR-0107).
        async with self._engine.begin() as conn:
            for write, audit in items:
                await self._write(conn, write)
                await write_audit(conn, case_id, audit)
            await touch(conn, case_id)

    @staticmethod
    async def _write(conn: AsyncConnection, write: RelationshipWrite) -> None:
        """Actualiza el vínculo guardado o guarda uno nuevo con su llave."""
        params: dict[str, Any] = {
            "id": write.relationship_id,
            "a": write.key.entity_a,
            "b": write.key.entity_b,
            "type": write.key.type.value,
            "label": write.custom_label,
            "origin": write.origin.value,
            "confidence": write.confidence,
            "status": write.review_status.value,
            "by": write.reviewer,
            "notes": write.notes,
        }
        if write.relationship_id is not None:
            await conn.execute(text(_UPDATE_SQL), params)
        else:
            await conn.execute(text(_INSERT_SQL), params)

    async def _stored(
        self,
        conn: AsyncConnection,
        root_of: Mapping[int, int],
        ends: Mapping[int, RelationshipEnd],
    ) -> dict[RelationshipKey, RowMapping]:
        """Los vínculos guardados entre entidades del caso, resueltos a sus raíces confirmadas."""
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT id, entity_a, entity_b, type, custom_label, origin, confidence, "
                        "review_status, reviewed_by, reviewed_at, notes FROM relationships "
                        "WHERE entity_a = ANY(:ids) AND entity_b = ANY(:ids) ORDER BY id"
                    ),
                    {"ids": list(root_of)},
                )
            )
            .mappings()
            .all()
        )
        found: dict[RelationshipKey, RowMapping] = {}
        for row in rows:
            first, second = root_of[row["entity_a"]], root_of[row["entity_b"]]
            # Las dos puntas quedaron en el mismo grupo, o alguna ya no está
            # confirmada: no se muestra (vuelve si se separa o se confirma).
            if first == second or first not in ends or second not in ends:
                continue
            key = _key(RelationshipType(row["type"]), first, second)
            current = found.get(key)
            priority = _REVIEW_PRIORITY[ReviewStatus(row["review_status"])]
            if (
                current is None
                or priority < _REVIEW_PRIORITY[ReviewStatus(current["review_status"])]
            ):
                found[key] = row
        return found

    @staticmethod
    def _shared(articles_of: Mapping[int, set[int]]) -> dict[tuple[int, int], set[int]]:
        """Pares de entidades confirmadas con las notas que comparten (id menor primero)."""
        roots_in: dict[int, list[int]] = defaultdict(list)
        for root in sorted(articles_of):
            for article in articles_of[root]:
                roots_in[article].append(root)
        shared: dict[tuple[int, int], set[int]] = defaultdict(set)
        for article, roots in roots_in.items():
            for index, first in enumerate(roots):
                for second in roots[index + 1 :]:
                    shared[(first, second)].add(article)
        return dict(shared)

    async def _articles(self, conn: AsyncConnection, ids: set[int]) -> dict[int, SharedArticle]:
        if not ids:
            return {}
        rows = await conn.execute(
            text(
                "SELECT id, title, url_canonical, published_at FROM articles WHERE id = ANY(:ids)"
            ),
            {"ids": sorted(ids)},
        )
        return {
            row["id"]: SharedArticle(
                row["id"], row["title"], row["url_canonical"], row["published_at"]
            )
            for row in rows.mappings()
        }

    @staticmethod
    def _evidence(
        ids: set[int], articles: Mapping[int, SharedArticle]
    ) -> tuple[SharedArticle, ...]:
        """Las notas compartidas, de la más reciente a la más vieja."""
        found = [articles[i] for i in ids if i in articles]
        return tuple(
            sorted(found, key=lambda a: (a.published_at or _UNDATED, a.article_id), reverse=True)
        )

    def _view(  # noqa: PLR0913 — un vínculo guardado con su evidencia ya calculada (*)
        self,
        key: RelationshipKey,
        *,
        row: RowMapping,
        ends: Mapping[int, RelationshipEnd],
        origin: Origin,
        confidence: float,
        evidence: set[int],
        articles: Mapping[int, SharedArticle],
    ) -> RelationshipView:
        return RelationshipView(
            relationship_id=row["id"],
            entity_a=ends[key.entity_a],
            entity_b=ends[key.entity_b],
            type=key.type,
            custom_label=row["custom_label"],
            origin=origin,
            confidence=confidence,
            review_status=ReviewStatus(row["review_status"]),
            reviewed_by=row["reviewed_by"],
            reviewed_at=row["reviewed_at"],
            notes=row["notes"],
            shared_articles=self._evidence(evidence, articles),
        )
