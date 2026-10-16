"""Índice local de notas y registro de ingesta sobre PostgreSQL (ADR-0013).

Implementa ``NewsIndexPort`` (``news_index``) e ``IngestRunLogPort``
(``ingest_runs``) con SQL explícito.

Una nota se identifica por el SHA-256 de su URL: si llega dos veces (de
GDELT y de un RSS, o en dos corridas), se guarda una sola vez. Cada corrida
trae ~100 notas, así que se insertan una por una dentro de una transacción;
el historial grande usa la misma vía en lotes por archivo.

No hace: no busca (eso es ``LocalIndexProvider``).
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.ports.ingest import IngestRun
from app.application.ports.local_index import IndexStats, SourceStats
from app.domain.news_index import NewsItem

_INSERT = text(
    """
    INSERT INTO news_index (source, url, url_hash, title, snippet, source_name, source_domain,
        published_at, language, text_norm, gdelt_states, gdelt_locations, gdelt_themes,
        body_terms)
    VALUES (:source, :url, :url_hash, :title, :snippet, :source_name, :source_domain,
        :published_at, :language, :text_norm, :gdelt_states, CAST(:gdelt_locations AS jsonb),
        :gdelt_themes, :body_terms)
    ON CONFLICT (url_hash) DO NOTHING
    RETURNING id
    """
)


def url_hash(url: str) -> str:
    """Huella de una URL para la llave única del índice.

    Args:
        url: URL de la nota.

    Returns:
        SHA-256 en hexadecimal.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _values(item: NewsItem) -> dict[str, object]:
    return {
        "source": item.source,
        "url": item.url,
        "url_hash": url_hash(item.url),
        "title": item.title,
        "snippet": item.snippet,
        "source_name": item.source_name,
        "source_domain": item.source_domain,
        "published_at": item.published_at,
        "language": item.language,
        "text_norm": item.text_norm,
        "gdelt_states": list(item.gdelt_states),
        "gdelt_locations": (
            json.dumps([asdict(loc) for loc in item.gdelt_locations], ensure_ascii=False)
            if item.gdelt_locations
            else None
        ),
        "gdelt_themes": list(item.gdelt_themes),
        "body_terms": item.body_terms,
    }


class PostgresNewsIndex:
    """Escritura y limpieza de ``news_index``."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def add(self, items: Sequence[NewsItem]) -> int:
        """Ver ``NewsIndexPort.add``."""
        new = 0
        async with self._engine.begin() as conn:
            for item in items:
                inserted = await conn.execute(_INSERT, _values(item))
                new += 1 if inserted.first() is not None else 0
        return new

    async def purge_before(self, cutoff: datetime) -> int:
        """Ver ``NewsIndexPort.purge_before`` (usa el índice por fecha)."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM news_index WHERE published_at < :cutoff"), {"cutoff": cutoff}
            )
            return result.rowcount

    async def clear_bodies_before(self, cutoff: datetime) -> int:
        """Ver ``NewsIndexPort.clear_bodies_before`` (usa el índice por fecha)."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "UPDATE news_index SET body_terms = NULL "
                    "WHERE published_at < :cutoff AND body_terms IS NOT NULL"
                ),
                {"cutoff": cutoff},
            )
            return result.rowcount


async def index_stats(engine: AsyncEngine) -> tuple[list[SourceStats], int]:
    """Resumen del índice por fuente y su tamaño total en disco.

    Lo usan el comando de muestra de ngramas y la pestaña "Notas".

    Args:
        engine: Engine asíncrono.

    Returns:
        Las estadísticas por fuente y los bytes de la tabla con sus índices.
    """
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                SELECT source, count(*) AS notes, count(body_terms) AS with_body,
                       coalesce(sum(pg_column_size(body_terms)), 0) AS body_bytes,
                       min(published_at) AS oldest, max(published_at) AS newest
                FROM news_index GROUP BY source ORDER BY source
                """
            )
        )
        stats = [SourceStats(**row) for row in rows.mappings()]
        total = await conn.execute(text("SELECT pg_total_relation_size('news_index')"))
        return stats, int(total.scalar_one())


class PostgresIndexStats:
    """``IndexStatsPort`` sobre PostgreSQL (pestaña temporal "Notas")."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def stats(self) -> IndexStats:
        """Ver ``IndexStatsPort.stats``."""
        sources, total = await index_stats(self._engine)
        async with self._engine.connect() as conn:
            last = await conn.execute(
                text("SELECT max(finished_at) FROM ingest_runs WHERE status = 'ok'")
            )
            last_run_at: datetime | None = last.scalar_one()
        return IndexStats(tuple(sources), total, last_run_at)


class PostgresIngestRunLog:
    """Escritura y consultas de ``ingest_runs``."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def already_processed(self, dedupe_key: str) -> bool:
        """Ver ``IngestRunLogPort.already_processed``."""
        async with self._engine.connect() as conn:
            found = await conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM ingest_runs "
                    "WHERE dedupe_key = :key AND status = 'ok')"
                ),
                {"key": dedupe_key},
            )
            return bool(found.scalar_one())

    async def record(self, run: IngestRun) -> int:
        """Ver ``IngestRunLogPort.record``.

        El reloj y el historial pueden terminar el mismo archivo casi a la
        vez; el segundo "ok" no rompe la llave única, simplemente no se guarda
        (las notas ya se deduplicaron por URL).
        """
        async with self._engine.begin() as conn:
            row_id: int | None = (
                await conn.execute(
                    text(
                        """
                        INSERT INTO ingest_runs (source, item, dedupe_key, status,
                            bytes_downloaded, items_seen, items_kept, items_new, error_message,
                            started_at, finished_at)
                        VALUES (:source, :item, :dedupe_key, :status, :bytes_downloaded,
                            :items_seen, :items_kept, :items_new, :error_message,
                            :started_at, :finished_at)
                        ON CONFLICT (dedupe_key)
                            WHERE status = 'ok' AND dedupe_key IS NOT NULL
                            DO NOTHING
                        RETURNING id
                        """
                    ),
                    asdict(run),
                )
            ).scalar_one_or_none()
            return row_id or 0
