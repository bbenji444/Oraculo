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
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.application.audit import SEARCH_FINISHED, Actor
from app.application.ports.llm import EnrichmentResult
from app.application.ports.search_store import (
    NewSearch,
    ProcessingErrorRecord,
    SearchClosing,
    SearchConcept,
    SearchResultRow,
    StoredArticle,
    StoredSearch,
)
from app.domain.dedupe import DedupedArticle, url_hash
from app.domain.enrichment import LLMUsage
from app.domain.extraction import ProcessingText
from app.domain.geocoding import Resolution
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
            await conn.execute(
                text("DELETE FROM article_locations WHERE article_id = :a"), {"a": article_id}
            )
            for r in resolutions:
                await conn.execute(
                    text(
                        """
                        INSERT INTO article_locations (article_id, mention_text, role, region_id,
                            precision, confidence, is_primary, point)
                        VALUES (:a, :mention, :role, :region, :precision, :confidence,
                            :primary, CASE WHEN CAST(:lon AS double precision) IS NULL THEN NULL
                                ELSE ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) END)
                        """
                    ),
                    {
                        "a": article_id,
                        "mention": r.mention.text,
                        "role": r.mention.role.value,
                        "region": r.place.region_id if r.place else None,
                        "precision": r.precision.value,
                        "confidence": r.confidence,
                        "primary": r.is_primary,
                        "lon": r.place.lon if r.place else None,
                        "lat": r.place.lat if r.place else None,
                    },
                )

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
