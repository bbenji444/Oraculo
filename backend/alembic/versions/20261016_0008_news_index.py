"""Crear news_index: índice local de notas que junta la ingesta (ADR-0013).

Cada 15 minutos la ingesta guarda aquí notas de los archivos GKG de GDELT
(en español, con alguna ubicación en México) y de los RSS de medios
mexicanos. El proveedor ``indice_local`` busca aquí al momento de buscar.

Solo metadatos y link (CLAUDE.md §8): título, fragmento, medio, fecha y, de
GDELT, sus ubicaciones y temas como **pistas** (no son la ubicación final).

Índices en la misma migración (CLAUDE.md §6.3):
- ``url_hash`` único: una nota se guarda una vez aunque llegue por dos vías.
- Trigramas sobre ``text_norm``: búsqueda de palabras clave.
- (``published_at``, ``id``): rango de fechas y limpieza por retención.
- GIN sobre ``gdelt_states``: notas que GDELT ubicó en un estado.
- (``source``, ``published_at``): conteos por fuente.

Revisión: 0008
Anterior: 0007
Fecha: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla y sus índices."""
    op.execute(
        """
        CREATE TABLE news_index (
            id               bigserial PRIMARY KEY,
            -- 'gdelt_gkg' o 'rss:<medio>' ('rss:la-jornada').
            source           text NOT NULL,
            url              text NOT NULL,
            -- SHA-256 de la URL: llave única corta (una URL puede ser muy larga).
            url_hash         text NOT NULL,
            title            text NOT NULL,
            snippet          text,
            source_name      text,
            source_domain    text,
            published_at     timestamptz NOT NULL,
            language         text,
            -- Título + fragmento normalizados (mayúsculas, sin acentos, con Ñ).
            text_norm        text NOT NULL,
            -- Claves INEGI de estado donde GDELT ubicó la nota ('09', '15'...).
            gdelt_states     text[] NOT NULL DEFAULT '{}',
            -- Ubicaciones y temas tal como los da GDELT (pistas para F4).
            gdelt_locations  jsonb,
            gdelt_themes     text[] NOT NULL DEFAULT '{}',
            ingested_at      timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT news_index_title_not_blank CHECK (btrim(title) <> ''),
            CONSTRAINT news_index_url_web CHECK (url ~ '^https?://')
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX news_index_url_hash_key ON news_index (url_hash)")
    op.execute("CREATE INDEX news_index_text_trgm ON news_index USING gin (text_norm gin_trgm_ops)")
    op.execute("CREATE INDEX news_index_published_id ON news_index (published_at, id)")
    op.execute("CREATE INDEX news_index_gdelt_states ON news_index USING gin (gdelt_states)")
    op.execute("CREATE INDEX news_index_source_published ON news_index (source, published_at)")


def downgrade() -> None:
    """Elimina el índice local (se pierden las notas juntadas)."""
    op.execute("DROP TABLE news_index")
