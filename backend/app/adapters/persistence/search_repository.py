"""``SearchStorePort`` y ``ArticleStorePort`` sobre PostgreSQL (especificación §6 y §9).

- ``PostgresSearchStore``: ``searches``, ``search_concepts``,
  ``processing_errors`` y la bitácora al cerrar (en la misma transacción).
- ``PostgresArticleStore``: ``articles`` (una por URL canónica, global),
  ``article_texts`` (solo para procesar, con retención), ``article_concepts``,
  ``article_locations`` (el punto sale del catálogo, nunca de la IA) y
  ``search_results``.

También trae dos lecturas para el comando ``make buscar``: el avance de una
búsqueda y una vista previa de sus resultados.

No hace: no decide nada (eso es ``RunSearch``).
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.application.audit import SEARCH_FINISHED, SEARCH_REPROCESSED, Actor
from app.application.pagination import TimeCursor
from app.application.ports.llm import EnrichmentResult
from app.application.ports.search_reads import (
    ArticleDetail,
    ArticleFilters,
    ArticleItem,
    ConceptRef,
    InRegion,
    JudgementView,
    LocationView,
    SearchDetail,
)
from app.application.ports.search_store import (
    ArticleMentions,
    NewSearch,
    ProcessingErrorRecord,
    SearchClosing,
    SearchConcept,
    SearchResultRow,
    StoredArticle,
    StoredSearch,
    StoredText,
)
from app.domain.dedupe import DedupedArticle, url_hash
from app.domain.enrichment import LLMUsage
from app.domain.extraction import ProcessingText
from app.domain.geocoding import MEXICO_ISO3, Mention, MentionRole, Resolution
from app.domain.region import RegionLevel
from app.domain.search import SearchStatus

AUDIT_ENTITY = "search"
# Texto máximo de un mensaje de error guardado: lo útil cabe y una respuesta
# enorme de un proveedor no llena la tabla.
MAX_ERROR_CHARS = 2000
_INSERT_AUDIT = (
    "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
    "VALUES (:user_id, :action, :entity_type, :entity_id, "
    "CAST(:payload AS jsonb), CAST(:ip AS inet))"
)


@dataclass(frozen=True, slots=True)
class SearchSnapshot:
    """Cómo va (o cómo terminó) una búsqueda.

    Attributes:
        status: Estado.
        progress: Etapa actual y conteos (``RunSearch``).
        credits_used: Créditos gastados.
        llm_usage: Tokens de la IA.
        llm_cost_usd: Costo estimado de la IA.
        error_summary: Qué falló, si algo falló.
    """

    status: SearchStatus
    progress: dict[str, object]
    credits_used: int
    llm_usage: LLMUsage
    llm_cost_usd: float
    error_summary: str | None


def _json(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, default=str)


class PostgresSearchStore:
    """La fila de ``searches`` y lo que cuelga de ella."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def create(self, search: NewSearch) -> UUID:
        """Ver ``SearchStorePort.create``."""
        async with self._engine.begin() as conn:
            search_id: UUID = (
                await conn.execute(
                    text(
                        "INSERT INTO searches (user_id, region_id, date_from, date_to, "
                        "queries_planned, credits_estimated) VALUES (:user_id, :region_id, "
                        ":date_from, :date_to, :queries, :credits) RETURNING id"
                    ),
                    {
                        "user_id": search.user_id,
                        "region_id": search.region_id,
                        "date_from": search.date_from,
                        "date_to": search.date_to,
                        "queries": search.queries_planned,
                        "credits": search.credits_estimated,
                    },
                )
            ).scalar_one()
            for concept in search.concepts:
                await conn.execute(
                    text(
                        "INSERT INTO search_concepts (search_id, concept_id, concept_name, "
                        "keywords, exclude_terms) VALUES (:s, :c, :name, :kw, :ex)"
                    ),
                    {
                        "s": search_id,
                        "c": concept.concept_id,
                        "name": concept.name,
                        "kw": list(concept.keywords),
                        "ex": list(concept.exclude_terms),
                    },
                )
        return search_id

    async def load(self, search_id: UUID) -> StoredSearch | None:
        """Ver ``SearchStorePort.load``."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT s.id, s.user_id, s.region_id, r.code, s.date_from, "
                            "s.date_to, s.status FROM searches s "
                            "JOIN regions r ON r.id = s.region_id WHERE s.id = :id"
                        ),
                        {"id": search_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            concepts = (
                (
                    await conn.execute(
                        text(
                            "SELECT sc.concept_id, sc.concept_name, c.description, sc.keywords, "
                            "sc.exclude_terms FROM search_concepts sc "
                            "JOIN concepts c ON c.id = sc.concept_id "
                            "WHERE sc.search_id = :id ORDER BY sc.concept_id"
                        ),
                        {"id": search_id},
                    )
                )
                .mappings()
                .all()
            )
        return StoredSearch(
            search_id=row["id"],
            user_id=row["user_id"],
            region_id=row["region_id"],
            region_code=row["code"],
            date_from=row["date_from"],
            date_to=row["date_to"],
            status=SearchStatus(row["status"]),
            concepts=tuple(
                SearchConcept(
                    c["concept_id"],
                    c["concept_name"],
                    c["description"],
                    tuple(c["keywords"]),
                    tuple(c["exclude_terms"]),
                )
                for c in concepts
            ),
        )

    async def start(self, search_id: UUID) -> None:
        """Ver ``SearchStorePort.start``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE searches SET status = 'running', started_at = now(), "
                    "updated_at = now() WHERE id = :id"
                ),
                {"id": search_id},
            )

    async def set_progress(self, search_id: UUID, progress: Mapping[str, object]) -> None:
        """Ver ``SearchStorePort.set_progress``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE searches SET progress = CAST(:p AS jsonb), updated_at = now() "
                    "WHERE id = :id"
                ),
                {"id": search_id, "p": _json(progress)},
            )

    async def record_error(self, error: ProcessingErrorRecord) -> None:
        """Ver ``SearchStorePort.record_error``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO processing_errors (search_id, article_id, stage, error_type, "
                    "message, payload) VALUES (:s, :a, :stage, :type, :message, "
                    "CAST(:payload AS jsonb))"
                ),
                {
                    "s": error.search_id,
                    "a": error.article_id,
                    "stage": error.stage.value,
                    "type": error.error_type,
                    "message": error.message[:MAX_ERROR_CHARS],
                    "payload": _json(error.payload),
                },
            )

    async def finish(self, search_id: UUID, closing: SearchClosing, actor: Actor) -> None:
        """Ver ``SearchStorePort.finish``."""
        async with self._engine.begin() as conn:
            params = (
                (
                    await conn.execute(
                        text(
                            "UPDATE searches SET status = :status, progress = CAST(:p AS jsonb), "
                            "credits_used = :credits, llm_tokens_in = :tin, "
                            "llm_tokens_out = :tout, llm_cost_usd = :cost, "
                            "results_count = :results, error_summary = :summary, "
                            "finished_at = now(), updated_at = now() WHERE id = :id "
                            "RETURNING region_id, date_from, date_to"
                        ),
                        {
                            "id": search_id,
                            "status": closing.status.value,
                            "p": _json(closing.progress),
                            "credits": closing.credits_used,
                            "tin": closing.llm_usage.tokens_in,
                            "tout": closing.llm_usage.tokens_out,
                            "cost": round(closing.llm_cost_usd, 4),
                            "results": closing.results_count,
                            "summary": closing.error_summary,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await _audit(conn, search_id, closing, actor, dict(params))

    async def fail(self, search_id: UUID, message: str) -> None:
        """Marca una búsqueda como ``failed`` por un error inesperado del worker.

        Args:
            search_id: Id.
            message: Qué pasó.
        """
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE searches SET status = 'failed', error_summary = :m, "
                    "finished_at = now(), updated_at = now() WHERE id = :id"
                ),
                {"id": search_id, "m": message[:MAX_ERROR_CHARS]},
            )

    async def search_detail(self, search_id: UUID) -> SearchDetail | None:
        """Ver ``SearchReaderPort.search_detail``."""
        rows = await self._details("s.id = :id", {"id": search_id}, 1)
        return rows[0] if rows else None

    async def history(
        self, user_id: str, after: TimeCursor | None, limit: int
    ) -> list[SearchDetail]:
        """Ver ``SearchReaderPort.history``."""
        where = "s.user_id = :user"
        params: dict[str, object] = {"user": user_id}
        if after is not None:
            where += " AND (s.created_at, s.id) < (:moment, CAST(:after_id AS uuid))"
            params.update({"moment": after.moment, "after_id": after.id})
        return await self._details(where, params, limit)

    async def _details(
        self, where: str, params: Mapping[str, object], limit: int
    ) -> list[SearchDetail]:
        async with self._engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            f"""
                            SELECT s.*, r.code AS region_code, r.name AS region_name,
                                COALESCE((SELECT json_agg(json_build_array(sc.concept_id,
                                    sc.concept_name) ORDER BY sc.concept_id)
                                    FROM search_concepts sc WHERE sc.search_id = s.id),
                                    '[]') AS concepts
                            FROM searches s JOIN regions r ON r.id = s.region_id
                            WHERE {where}
                            ORDER BY s.created_at DESC, s.id DESC
                            LIMIT :limit
                            """  # noqa: S608 — where se arma con texto fijo de este módulo
                        ),
                        {**params, "limit": limit},
                    )
                )
                .mappings()
                .all()
            )
        return [
            SearchDetail(
                search_id=row["id"],
                user_id=row["user_id"],
                status=SearchStatus(row["status"]),
                region_id=row["region_id"],
                region_code=row["region_code"],
                region_name=row["region_name"],
                date_from=row["date_from"],
                date_to=row["date_to"],
                concepts=tuple(ConceptRef(c[0], c[1]) for c in row["concepts"]),
                progress=dict(row["progress"]),
                queries_planned=row["queries_planned"],
                credits_estimated=row["credits_estimated"],
                credits_used=row["credits_used"],
                llm_usage=LLMUsage(row["llm_tokens_in"], row["llm_tokens_out"]),
                llm_cost_usd=float(row["llm_cost_usd"]),
                results_count=row["results_count"],
                error_summary=row["error_summary"],
                created_at=row["created_at"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in rows
        ]

    async def last_search_id(self) -> UUID | None:
        """La búsqueda más reciente (para ``make reubicar`` sin id).

        Returns:
            Su id, o ``None`` si no hay búsquedas.
        """
        async with self._engine.connect() as conn:
            found: UUID | None = (
                await conn.execute(
                    text("SELECT id FROM searches ORDER BY created_at DESC, id DESC LIMIT 1")
                )
            ).scalar()
        return found

    async def snapshot(self, search_id: UUID) -> SearchSnapshot | None:
        """Cómo va una búsqueda (el comando lo consulta mientras corre en el worker).

        Args:
            search_id: Id.

        Returns:
            Estado, avance y costos, o ``None`` si no existe.
        """
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT status, progress, credits_used, llm_tokens_in, "
                            "llm_tokens_out, llm_cost_usd, error_summary FROM searches "
                            "WHERE id = :id"
                        ),
                        {"id": search_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return SearchSnapshot(
            status=SearchStatus(row["status"]),
            progress=dict(row["progress"]),
            credits_used=row["credits_used"],
            llm_usage=LLMUsage(row["llm_tokens_in"], row["llm_tokens_out"]),
            llm_cost_usd=float(row["llm_cost_usd"]),
            error_summary=row["error_summary"],
        )


async def _audit(
    conn: AsyncConnection,
    search_id: UUID,
    closing: SearchClosing,
    actor: Actor,
    params: Mapping[str, object],
) -> None:
    payload = {
        "region_id": params["region_id"],
        "desde": params["date_from"],
        "hasta": params["date_to"],
        "estado": closing.status.value,
        "consultas": list(closing.queries_executed),
        "creditos": closing.credits_used,
        "tokens_entrada": closing.llm_usage.tokens_in,
        "tokens_salida": closing.llm_usage.tokens_out,
        "costo_ia_usd": round(closing.llm_cost_usd, 4),
        "notas": closing.results_count,
    }
    await conn.execute(
        text(_INSERT_AUDIT),
        {
            "user_id": actor.user_id,
            "action": SEARCH_FINISHED,
            "entity_type": AUDIT_ENTITY,
            "entity_id": str(search_id),
            "payload": _json(payload),
            "ip": actor.ip,
        },
    )


@dataclass(frozen=True, slots=True)
class ResultPreview:
    """Una nota de una búsqueda, tal como la muestra ``make buscar``.

    Attributes:
        title: Título.
        source: Medio.
        url: Link.
        published_at: Fecha de publicación.
        summary: Resumen de la IA.
        concepts: Conceptos para los que es relevante.
        place: Ubicación principal ("Alcaldía Iztapalapa").
        precision: Precisión de esa ubicación.
        confidence: Confianza.
        in_region: Si cae en la región buscada.
        extraction_status: ``ok`` o ``fallback``.
    """

    title: str
    source: str | None
    url: str
    published_at: datetime | None
    summary: str | None
    concepts: tuple[str, ...]
    place: str | None
    precision: str | None
    confidence: float | None
    in_region: bool | None
    extraction_status: str


class PostgresArticleStore:
    """Notas, su texto, su enriquecimiento y sus ubicaciones."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def upsert(self, articles: Sequence[DedupedArticle]) -> list[StoredArticle]:
        """Ver ``ArticleStorePort.upsert``."""
        if not articles:
            return []
        ids: list[int] = []
        async with self._engine.begin() as conn:
            for item in articles:
                a = item.article
                ids.append(
                    (
                        await conn.execute(
                            text(
                                """
                                INSERT INTO articles (url_canonical, url_hash, title, title_norm,
                                    source_name, source_domain, published_at, snippet, language)
                                VALUES (:url, :hash, :title, :title_norm, :source_name,
                                    :source_domain, :published_at, :snippet, :language)
                                ON CONFLICT (url_hash) DO UPDATE SET updated_at = now()
                                RETURNING id
                                """
                            ),
                            {
                                "url": item.url_canonical,
                                "hash": url_hash(item.url_canonical),
                                "title": a.title,
                                "title_norm": item.title_norm,
                                "source_name": a.source_name,
                                "source_domain": a.source_domain,
                                "published_at": a.published_at,
                                "snippet": a.snippet,
                                "language": a.language,
                            },
                        )
                    ).scalar_one()
                )
            known = (
                (
                    await conn.execute(
                        text(
                            """
                            SELECT a.id,
                                CASE WHEN a.enrichment_status = 'ok' THEN a.prompt_version END
                                    AS prompt_version,
                                COALESCE((SELECT array_agg(ac.concept_id) FROM article_concepts ac
                                    WHERE ac.article_id = a.id), '{}') AS concept_ids,
                                (SELECT r.code FROM article_locations al
                                    JOIN regions r ON r.id = al.region_id
                                    WHERE al.article_id = a.id AND al.is_primary) AS primary_code
                            FROM articles a WHERE a.id = ANY(:ids)
                            """
                        ),
                        {"ids": ids},
                    )
                )
                .mappings()
                .all()
            )
        by_id = {
            row["id"]: StoredArticle(
                row["id"],
                row["prompt_version"],
                frozenset(row["concept_ids"]),
                row["primary_code"],
            )
            for row in known
        }
        return [by_id[i] for i in ids]

    async def save_text(self, article_id: int, text_: ProcessingText) -> None:
        """Ver ``ArticleStorePort.save_text``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO article_texts (article_id, body) VALUES (:id, :body) "
                    "ON CONFLICT (article_id) DO UPDATE SET body = EXCLUDED.body, "
                    "extracted_at = now()"
                ),
                {"id": article_id, "body": text_.text},
            )
            await conn.execute(
                text(
                    "UPDATE articles SET extraction_status = :status, text_hash = :hash, "
                    "updated_at = now() WHERE id = :id"
                ),
                {"id": article_id, "status": text_.status.value, "hash": text_.text_hash},
            )

    async def save_enrichment(
        self, article_id: int, result: EnrichmentResult, resolutions: Sequence[Resolution]
    ) -> None:
        """Ver ``ArticleStorePort.save_enrichment``."""
        enrichment = result.enrichment
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE articles SET summary = :summary, event_type = :event_type, "
                    "event_date = :event_date, enrichment_status = 'ok', llm_model = :model, "
                    "prompt_version = :prompt, updated_at = now() WHERE id = :id"
                ),
                {
                    "id": article_id,
                    "summary": enrichment.summary,
                    "event_type": enrichment.event_type,
                    "event_date": enrichment.event_date,
                    "model": result.model,
                    "prompt": result.prompt_version,
                },
            )
            for judgement in enrichment.concepts:
                await conn.execute(
                    text(
                        "INSERT INTO article_concepts (article_id, concept_id, is_relevant, "
                        "relevance_score, relevance_reason) VALUES (:a, :c, :rel, :score, "
                        ":reason) ON CONFLICT (article_id, concept_id) DO UPDATE SET "
                        "is_relevant = EXCLUDED.is_relevant, "
                        "relevance_score = EXCLUDED.relevance_score, "
                        "relevance_reason = EXCLUDED.relevance_reason"
                    ),
                    {
                        "a": article_id,
                        "c": judgement.concept_id,
                        "rel": judgement.is_relevant,
                        "score": judgement.relevance_score,
                        "reason": judgement.relevance_reason,
                    },
                )
            await _write_locations(conn, article_id, resolutions)

    async def mark_enrichment_failed(self, article_id: int) -> None:
        """Ver ``ArticleStorePort.mark_enrichment_failed``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE articles SET enrichment_status = 'failed', updated_at = now() "
                    "WHERE id = :id AND enrichment_status <> 'ok'"
                ),
                {"id": article_id},
            )

    async def link_results(self, search_id: UUID, rows: Sequence[SearchResultRow]) -> None:
        """Ver ``ArticleStorePort.link_results``."""
        async with self._engine.begin() as conn:
            for row in rows:
                await conn.execute(
                    text(
                        "INSERT INTO search_results (search_id, article_id, provider, "
                        "provider_rank, in_region) VALUES (:s, :a, :p, :rank, :inside) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "s": search_id,
                        "a": row.article_id,
                        "p": row.provider,
                        "rank": row.provider_rank,
                        "inside": row.in_region,
                    },
                )

    async def search_mentions(self, search_id: UUID) -> list[ArticleMentions]:
        """Ver ``RelocationStorePort.search_mentions``."""
        async with self._engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            """
                            SELECT a.id, a.title, al.mention_text, al.role, al.kind_hint,
                                al.state_hint,
                                -- Filas anteriores a 0014: si se resolvió a otro país,
                                -- ese país es la pista.
                                COALESCE(al.country_hint, CASE WHEN r.level = 'country'
                                    AND r.code <> :mx THEN r.name END) AS country,
                                (SELECT pr.code FROM article_locations p
                                    JOIN regions pr ON pr.id = p.region_id
                                    WHERE p.article_id = a.id AND p.is_primary) AS primary_code
                            FROM (SELECT DISTINCT article_id FROM search_results
                                  WHERE search_id = :s) sr
                            JOIN articles a ON a.id = sr.article_id
                            LEFT JOIN article_locations al ON al.article_id = a.id
                            LEFT JOIN regions r ON r.id = al.region_id
                            ORDER BY a.id, al.id
                            """
                        ),
                        {"s": search_id, "mx": MEXICO_ISO3},
                    )
                )
                .mappings()
                .all()
            )
        grouped: dict[int, ArticleMentions] = {}
        for row in rows:
            current = grouped.get(row["id"]) or ArticleMentions(
                row["id"], row["title"], (), row["primary_code"]
            )
            if row["mention_text"] is not None:
                mention = Mention(
                    row["mention_text"],
                    MentionRole(row["role"]),
                    RegionLevel(row["kind_hint"]) if row["kind_hint"] else None,
                    row["state_hint"],
                    row["country"],
                )
                current = replace(current, mentions=(*current.mentions, mention))
            grouped[row["id"]] = current
        return list(grouped.values())

    async def save_locations(self, article_id: int, resolutions: Sequence[Resolution]) -> None:
        """Ver ``RelocationStorePort.save_locations``."""
        async with self._engine.begin() as conn:
            await _write_locations(conn, article_id, resolutions)

    async def set_in_region(self, search_id: UUID, article_id: int, in_region: bool | None) -> None:
        """Ver ``RelocationStorePort.set_in_region``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE search_results SET in_region = :inside "
                    "WHERE search_id = :s AND article_id = :a"
                ),
                {"s": search_id, "a": article_id, "inside": in_region},
            )

    async def merge_progress(self, search_id: UUID, values: Mapping[str, object]) -> None:
        """Ver ``RelocationStorePort.merge_progress``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE searches SET progress = progress || CAST(:p AS jsonb), "
                    "updated_at = now() WHERE id = :s"
                ),
                {"s": search_id, "p": _json(values)},
            )

    async def search_texts(self, search_id: UUID) -> list[StoredText]:
        """Ver ``ReprocessStorePort.search_texts``."""
        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT a.id, a.title, t.body, a.published_at FROM articles a "
                        "JOIN article_texts t ON t.article_id = a.id "
                        "WHERE a.id IN (SELECT article_id FROM search_results "
                        "WHERE search_id = :s) ORDER BY a.id"
                    ),
                    {"s": search_id},
                )
            ).all()
        return [StoredText(r[0], r[1], r[2], r[3]) for r in rows]

    async def add_llm_usage(
        self, search_id: UUID, usage: LLMUsage, cost_usd: float, actor: Actor
    ) -> None:
        """Ver ``ReprocessStorePort.add_llm_usage``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE searches SET llm_tokens_in = llm_tokens_in + :tin, "
                    "llm_tokens_out = llm_tokens_out + :tout, "
                    "llm_cost_usd = llm_cost_usd + :cost, updated_at = now() WHERE id = :s"
                ),
                {
                    "s": search_id,
                    "tin": usage.tokens_in,
                    "tout": usage.tokens_out,
                    "cost": round(cost_usd, 4),
                },
            )
            await conn.execute(
                text(_INSERT_AUDIT),
                {
                    "user_id": actor.user_id,
                    "action": SEARCH_REPROCESSED,
                    "entity_type": AUDIT_ENTITY,
                    "entity_id": str(search_id),
                    "payload": _json(
                        {
                            "tokens_entrada": usage.tokens_in,
                            "tokens_salida": usage.tokens_out,
                            "costo_ia_usd": round(cost_usd, 4),
                        }
                    ),
                    "ip": actor.ip,
                },
            )

    async def search_articles(
        self, search_id: UUID, filters: ArticleFilters, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        """Ver ``ArticleReaderPort.search_articles``."""
        where, params = _article_filters(filters)
        params.update({"s": search_id, "limit": limit})
        if after is not None:
            # Orden: fecha de publicación de la más reciente a la más vieja, las
            # que no tienen fecha al final, y en empate por id descendente.
            if after.moment is None:
                where.append("a.published_at IS NULL AND a.id < :after_id")
            else:
                where.append(
                    "(a.published_at < :after_moment OR a.published_at IS NULL "
                    "OR (a.published_at = :after_moment AND a.id < :after_id))"
                )
                params["after_moment"] = after.moment
            params["after_id"] = int(after.id)
        sql = f"""
            SELECT {_ARTICLE_COLUMNS}, sr.in_region, sr.providers, {_PRIMARY_COLUMNS},
                {_JUDGEMENTS_IN_SEARCH} AS judgements
            FROM (SELECT article_id, bool_or(in_region) AS in_region,
                    array_agg(provider ORDER BY provider_rank, provider) AS providers
                  FROM search_results WHERE search_id = :s GROUP BY article_id) sr
            JOIN articles a ON a.id = sr.article_id
            LEFT JOIN article_locations p ON p.article_id = a.id AND p.is_primary
            LEFT JOIN regions r ON r.id = p.region_id
            WHERE {" AND ".join(where) or "true"}
            ORDER BY a.published_at DESC NULLS LAST, a.id DESC
            LIMIT :limit
        """  # noqa: S608 — columnas y condiciones son texto fijo de este módulo
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(sql), params)).mappings().all()
        return [_article_item(row) for row in rows]

    async def article_detail(self, article_id: int) -> ArticleDetail | None:
        """Ver ``ArticleReaderPort.article_detail``."""
        sql = f"""
            SELECT {_ARTICLE_COLUMNS}, a.first_seen_at, a.llm_model, a.prompt_version,
                (SELECT bool_or(in_region) FROM search_results WHERE article_id = a.id)
                    AS in_region,
                ARRAY(SELECT DISTINCT provider FROM search_results WHERE article_id = a.id
                    ORDER BY provider) AS providers,
                {_PRIMARY_COLUMNS},
                COALESCE((SELECT json_agg(json_build_array(ac.concept_id, c.name,
                    ac.is_relevant, ac.relevance_score, ac.relevance_reason)
                    ORDER BY ac.concept_id)
                    FROM article_concepts ac JOIN concepts c ON c.id = ac.concept_id
                    WHERE ac.article_id = a.id), '[]') AS judgements
            FROM articles a
            LEFT JOIN article_locations p ON p.article_id = a.id AND p.is_primary
            LEFT JOIN regions r ON r.id = p.region_id
            WHERE a.id = :id
        """  # noqa: S608 — columnas fijas de este módulo
        async with self._engine.connect() as conn:
            row = (await conn.execute(text(sql), {"id": article_id})).mappings().first()
            if row is None:
                return None
            locations = (
                (
                    await conn.execute(
                        text(
                            f"SELECT {_LOCATION_COLUMNS} FROM article_locations p "  # noqa: S608 — columnas fijas
                            "LEFT JOIN regions r ON r.id = p.region_id "
                            "WHERE p.article_id = :id ORDER BY p.id"
                        ),
                        {"id": article_id},
                    )
                )
                .mappings()
                .all()
            )
        return ArticleDetail(
            item=_article_item(row),
            locations=tuple(_location(loc) for loc in locations),
            first_seen_at=row["first_seen_at"],
            llm_model=row["llm_model"],
            prompt_version=row["prompt_version"],
        )

    async def purge_texts(self, older_than_days: int) -> int:
        """Borra los textos extraídos más viejos que la retención (ADR-0015).

        Args:
            older_than_days: ``ARTICLE_TEXT_RETENTION_DAYS``.

        Returns:
            Cuántos textos se borraron (la nota, su resumen y su link se quedan).
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "DELETE FROM article_texts "
                    "WHERE extracted_at < now() - make_interval(days => :days)"
                ),
                {"days": older_than_days},
            )
        return result.rowcount

    async def preview(self, search_id: UUID, limit: int) -> list[ResultPreview]:
        """Primeras notas de una búsqueda: enriquecidas, ubicadas y dentro de la región primero.

        Args:
            search_id: Búsqueda.
            limit: Cuántas.

        Returns:
            Las notas para mostrar.
        """
        async with self._engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            """
                            SELECT a.title, a.source_name, a.url_canonical, a.published_at,
                                a.summary, a.extraction_status, sr.in_region, sr.best_rank,
                                al.precision, al.confidence,
                                CASE WHEN r.level IN ('municipality', 'locality')
                                    THEN r.display_prefix || ' ' || r.name ELSE r.name END
                                    AS place,
                                COALESCE((SELECT array_agg(sc.concept_name ORDER BY sc.concept_name)
                                    FROM article_concepts ac JOIN search_concepts sc
                                        ON sc.concept_id = ac.concept_id AND sc.search_id = :s
                                    WHERE ac.article_id = a.id AND ac.is_relevant), '{}')
                                    AS concepts
                            FROM (SELECT article_id, bool_or(in_region) AS in_region,
                                    min(provider_rank) AS best_rank
                                  FROM search_results WHERE search_id = :s
                                  GROUP BY article_id) sr
                            JOIN articles a ON a.id = sr.article_id
                            LEFT JOIN article_locations al
                                ON al.article_id = a.id AND al.is_primary
                            LEFT JOIN regions r ON r.id = al.region_id
                            ORDER BY (a.enrichment_status = 'ok') DESC,
                                (al.id IS NOT NULL) DESC, sr.in_region DESC NULLS LAST,
                                sr.best_rank, a.id
                            LIMIT :n
                            """
                        ),
                        {"s": search_id, "n": limit},
                    )
                )
                .mappings()
                .all()
            )
        return [
            ResultPreview(
                title=row["title"],
                source=row["source_name"],
                url=row["url_canonical"],
                published_at=row["published_at"],
                summary=row["summary"],
                concepts=tuple(row["concepts"]),
                place=row["place"],
                precision=row["precision"],
                confidence=row["confidence"],
                in_region=row["in_region"],
                extraction_status=row["extraction_status"],
            )
            for row in rows
        ]


async def _write_locations(
    conn: AsyncConnection, article_id: int, resolutions: Sequence[Resolution]
) -> None:
    """Reemplaza las ubicaciones de una nota, con las pistas de la IA para reubicar después."""
    await conn.execute(
        text("DELETE FROM article_locations WHERE article_id = :a"), {"a": article_id}
    )
    for r in resolutions:
        mention = r.mention
        await conn.execute(
            text(
                """
                INSERT INTO article_locations (article_id, mention_text, role, kind_hint,
                    state_hint, country_hint, region_id, precision, confidence, is_primary,
                    point)
                VALUES (:a, :mention, :role, :kind, :state, :country, :region, :precision,
                    :confidence, :primary,
                    CASE WHEN CAST(:lon AS double precision) IS NULL THEN NULL
                        ELSE ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) END)
                """
            ),
            {
                "a": article_id,
                "mention": mention.text,
                "role": mention.role.value,
                "kind": mention.kind_hint.value if mention.kind_hint else None,
                "state": mention.state_hint,
                "country": mention.country,
                "region": r.place.region_id if r.place else None,
                "precision": r.precision.value,
                "confidence": r.confidence,
                "primary": r.is_primary,
                "lon": r.place.lon if r.place else None,
                "lat": r.place.lat if r.place else None,
            },
        )


_ARTICLE_COLUMNS = """
    a.id, a.title, a.source_name, a.source_domain, a.url_canonical, a.published_at,
    a.summary, a.event_type, a.event_date, a.extraction_status, a.enrichment_status
"""
_LOCATION_COLUMNS = """
    p.mention_text, p.role, p.precision, p.confidence, p.is_primary, r.id AS region_id,
    r.code AS region_code, r.level::text AS region_level, r.name AS region_name,
    r.display_prefix, ST_X(p.point) AS lon, ST_Y(p.point) AS lat
"""
# La ubicación principal, con el prefijo "p_" para no chocar con las de la nota.
_PRIMARY_COLUMNS = """
    p.id AS p_id, p.mention_text AS p_mention_text, p.role AS p_role,
    p.precision AS p_precision, p.confidence AS p_confidence, p.is_primary AS p_is_primary,
    r.id AS p_region_id, r.code AS p_region_code, r.level::text AS p_region_level,
    r.name AS p_region_name, r.display_prefix AS p_display_prefix,
    ST_X(p.point) AS p_lon, ST_Y(p.point) AS p_lat
"""
# Juicios de la IA para los conceptos de la búsqueda, con su nombre de entonces.
_JUDGEMENTS_IN_SEARCH = """
    COALESCE((SELECT json_agg(json_build_array(ac.concept_id, sc.concept_name,
        ac.is_relevant, ac.relevance_score, ac.relevance_reason) ORDER BY ac.concept_id)
        FROM article_concepts ac JOIN search_concepts sc
            ON sc.concept_id = ac.concept_id AND sc.search_id = :s
        WHERE ac.article_id = a.id), '[]')
"""
_UNKNOWN = "unknown"


def _article_filters(filters: ArticleFilters) -> tuple[list[str], dict[str, object]]:
    """Condiciones SQL (texto fijo) y sus parámetros para los filtros de notas."""
    where: list[str] = []
    params: dict[str, object] = {}
    judged = (
        "EXISTS (SELECT 1 FROM article_concepts ac JOIN search_concepts sc "
        "ON sc.concept_id = ac.concept_id AND sc.search_id = :s WHERE ac.article_id = a.id"
    )
    if filters.relevant_only:
        judged += " AND ac.is_relevant"
    if filters.concept_id is not None:
        judged += " AND ac.concept_id = :concept_id"
        params["concept_id"] = filters.concept_id
    if filters.relevant_only or filters.concept_id is not None:
        where.append(judged + ")")
    if filters.in_region is InRegion.INSIDE:
        where.append("sr.in_region IS TRUE")
    elif filters.in_region is InRegion.OUTSIDE:
        where.append("sr.in_region IS FALSE")
    elif filters.in_region is InRegion.UNLOCATED:
        where.append("sr.in_region IS NULL")
    if filters.precisions:
        located = sorted(filters.precisions - {_UNKNOWN})
        parts = ["p.precision = ANY(:precisions)"] if located else []
        if _UNKNOWN in filters.precisions:
            parts.append("p.id IS NULL")
        where.append(f"({' OR '.join(parts)})")
        params["precisions"] = located
    return where, params


def _place_name(level: str | None, prefix: str | None, name: str | None) -> str | None:
    # Igual que Region.display_name: municipios y localidades con su prefijo.
    if name is None:
        return None
    if level in ("municipality", "locality") and prefix:
        return f"{prefix} {name}"
    return name


def _location(row: RowMapping, prefix: str = "") -> LocationView:
    return LocationView(
        mention=row[f"{prefix}mention_text"],
        role=row[f"{prefix}role"],
        precision=row[f"{prefix}precision"],
        confidence=float(row[f"{prefix}confidence"]),
        is_primary=row[f"{prefix}is_primary"],
        region_id=row[f"{prefix}region_id"],
        region_code=row[f"{prefix}region_code"],
        place=_place_name(
            row[f"{prefix}region_level"],
            row[f"{prefix}display_prefix"],
            row[f"{prefix}region_name"],
        ),
        lon=row[f"{prefix}lon"],
        lat=row[f"{prefix}lat"],
    )


def _article_item(row: RowMapping) -> ArticleItem:
    return ArticleItem(
        article_id=row["id"],
        title=row["title"],
        source_name=row["source_name"],
        source_domain=row["source_domain"],
        url=row["url_canonical"],
        published_at=row["published_at"],
        summary=row["summary"],
        event_type=row["event_type"],
        event_date=row["event_date"],
        extraction_status=row["extraction_status"],
        enrichment_status=row["enrichment_status"],
        judgements=tuple(
            JudgementView(j[0], j[1], j[2], float(j[3]), j[4]) for j in row["judgements"]
        ),
        primary=_location(row, "p_") if row["p_id"] is not None else None,
        in_region=row["in_region"],
        providers=tuple(row["providers"]),
    )
