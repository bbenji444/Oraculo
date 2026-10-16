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
from app.domain.news_index import NewsItem

_INSERT = text(
    """
    INSERT INTO news_index (source, url, url_hash, title, snippet, source_name, source_domain,
        published_at, language, text_norm, gdelt_states, gdelt_locations, gdelt_themes)
    VALUES (:source, :url, :url_hash, :title, :snippet, :source_name, :source_domain,
        :published_at, :language, :text_norm, :gdelt_states, CAST(:gdelt_locations AS jsonb),
        :gdelt_themes)
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
        """Ver ``IngestRunLogPort.record``."""
        async with self._engine.begin() as conn:
            row_id: int = (
                await conn.execute(
                    text(
                        """
                        INSERT INTO ingest_runs (source, item, dedupe_key, status,
                            bytes_downloaded, items_seen, items_kept, items_new, error_message,
                            started_at, finished_at)
                        VALUES (:source, :item, :dedupe_key, :status, :bytes_downloaded,
                            :items_seen, :items_kept, :items_new, :error_message,
                            :started_at, :finished_at)
                        RETURNING id
                        """
                    ),
                    asdict(run),
                )
            ).scalar_one()
            return row_id
