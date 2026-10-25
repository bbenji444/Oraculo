"""Índice local de notas y registro de ingesta sobre PostgreSQL (ADR-0013).

Implementa ``NewsIndexPort`` (``news_index``), ``IngestRunLogPort``
(``ingest_runs``) e ``IndexCleanupPort`` (``make limpiar-duplicados``) con
SQL explícito.

Una nota se identifica por el SHA-256 de su URL canónica: si llega dos veces
(de GDELT y de un RSS, o en dos corridas), se guarda una sola vez. Tampoco
entra dos veces el mismo texto del mismo medio a ±3 días (ADR-0025). Cada corrida
trae ~100 notas, así que se insertan una por una dentro de una transacción;
el historial grande usa la misma vía en lotes por archivo.

No hace: no busca (eso es ``LocalIndexProvider``).
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.ports.ingest import IngestRun
from app.domain.dedupe import canonical_url
from app.domain.index_cleanup import IndexKey
from app.domain.news_index import SAME_OUTLET_WINDOW, NewsItem


@dataclass(frozen=True, slots=True)
class SourceStats:
    """Cuánto hay de una fuente en el índice (lo muestra ``make ngramas-muestra``).

    Attributes:
        source: ``gdelt_gkg``, ``gdelt_ngrams`` o ``rss:<medio>``.
        notes: Notas guardadas.
        with_body: Notas que conservan frases del cuerpo.
        body_bytes: Bytes que ocupan esas frases en disco (ya comprimidas).
        oldest: Nota más vieja (UTC), o ``None``.
        newest: Nota más nueva (UTC), o ``None``.
    """

    source: str
    notes: int
    with_body: int
    body_bytes: int
    oldest: datetime | None
    newest: datetime | None


# Dos reglas de duplicados (ADR-0025): la misma URL canónica no entra dos
# veces (``ON CONFLICT``), y el mismo medio con el mismo texto y el mismo
# cuerpo a ±SAME_OUTLET_WINDOW tampoco (``NOT EXISTS``, con el índice
# news_index_domain_published de la migración 0023). La misma nota en otro
# medio (sindicada) sí entra: es otra fuente.
_INSERT = text(
    """
    INSERT INTO news_index (source, url, url_hash, title, snippet, source_name, source_domain,
        published_at, language, text_norm, gdelt_states, gdelt_locations, gdelt_themes,
        body_terms)
    SELECT :source, :url, :url_hash, :title, :snippet, :source_name, :source_domain,
        :published_at, :language, :text_norm, :gdelt_states, CAST(:gdelt_locations AS jsonb),
        :gdelt_themes, :body_terms
    WHERE NOT EXISTS (
        SELECT 1 FROM news_index n
        WHERE n.source_domain = :source_domain
          AND n.published_at BETWEEN :window_from AND :window_to
          AND n.text_norm = :text_norm
          AND n.body_terms IS NOT DISTINCT FROM CAST(:body_terms AS text)
    )
    ON CONFLICT (url_hash) DO NOTHING
    RETURNING id
    """
)


def url_hash(url: str) -> str:
    """Huella de una URL para la llave única del índice.

    Se calcula sobre la URL canónica (sin ``www.``, puerto por defecto ni
    parámetros de rastreo): ``https://razon.com.mx:443/a`` y
    ``https://www.razon.com.mx/a`` son la misma nota (F12.1b).

    Args:
        url: URL de la nota, tal como llegó.

    Returns:
        SHA-256 en hexadecimal.
    """
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()


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
        "window_from": item.published_at - SAME_OUTLET_WINDOW,
        "window_to": item.published_at + SAME_OUTLET_WINDOW,
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

    Lo usa el comando de muestra de ngramas (``make ngramas-muestra``).

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


class PostgresIndexCleanup:
    """``IndexCleanupPort`` sobre ``news_index`` (``make limpiar-duplicados``).

    Args:
        engine: Engine asíncrono de SQLAlchemy.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def fetch_keys(self, after_id: int, limit: int) -> Sequence[IndexKey]:
        """Ver ``IndexCleanupPort.fetch_keys`` (cursor por id, nunca OFFSET)."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    """
                    SELECT id, url, url_hash, title, source_domain, text_norm, published_at,
                        body_terms IS NOT NULL AS has_body, md5(body_terms) AS body_fingerprint
                    FROM news_index WHERE id > :after ORDER BY id LIMIT :limit
                    """
                ),
                {"after": after_id, "limit": limit},
            )
            return [
                IndexKey(
                    note_id=r.id,
                    url=r.url,
                    url_hash=r.url_hash,
                    title=r.title,
                    source_domain=r.source_domain,
                    text_norm=r.text_norm,
                    published_at=r.published_at,
                    has_body=r.has_body,
                    body_fingerprint=r.body_fingerprint,
                )
                for r in rows
            ]

    async def delete(self, note_ids: Sequence[int]) -> int:
        """Ver ``IndexCleanupPort.delete``."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM news_index WHERE id = ANY(:ids)"), {"ids": list(note_ids)}
            )
            return result.rowcount

    async def rehash(self, pairs: Sequence[tuple[int, str]]) -> None:
        """Ver ``IndexCleanupPort.rehash``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE news_index n SET url_hash = v.hash
                    FROM unnest(CAST(:ids AS bigint[]), CAST(:hashes AS text[])) AS v(id, hash)
                    WHERE n.id = v.id
                    """
                ),
                {"ids": [p[0] for p in pairs], "hashes": [p[1] for p in pairs]},
            )
