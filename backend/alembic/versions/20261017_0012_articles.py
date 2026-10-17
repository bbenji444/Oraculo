"""Crear articles y sus tablas hijas: notas deduplicadas, enriquecidas y ubicadas (§6).

- ``articles``: una fila por nota en todo el sistema (deduplicada por URL
  canónica). Guarda metadatos, el resumen propio de la IA y su estado; nunca
  el texto completo (CLAUDE.md §8).
- ``article_texts``: el texto extraído, **solo para procesar**; se borra a
  los ``ARTICLE_TEXT_RETENTION_DAYS`` días (ADR-0015).
- ``article_concepts``: relevancia de cada nota para cada concepto.
- ``article_locations``: cada mención de lugar resuelta contra el catálogo
  INEGI, con su precisión y confianza (§11). El punto sale del catálogo, nunca
  de la IA.
- ``search_results``: qué notas encontró cada búsqueda y con qué proveedor.

Índices en la misma migración (CLAUDE.md §6.3): llave única por
``url_hash``, (``published_at``, ``id``) para paginar, trigramas de
``title_norm`` para casi duplicados, ``text_hash`` para la caché de la IA, y
los de cada llave foránea; GIST del punto para el mapa.

Revisión: 0012
Anterior: 0011
Fecha: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las tablas y sus índices."""
    op.execute(
        """
        CREATE TABLE articles (
            id                 bigserial PRIMARY KEY,
            url_canonical      text NOT NULL,
            -- SHA-256 de la URL canónica: llave única corta.
            url_hash           text NOT NULL,
            title              text NOT NULL,
            title_norm         text NOT NULL,
            source_name        text,
            source_domain      text,
            published_at       timestamptz,
            snippet            text,
            language           text,
            -- pending: sin extraer; ok: con texto; fallback: título + fragmento.
            extraction_status  text NOT NULL DEFAULT 'pending',
            text_hash          text,
            summary            text,
            event_type         text,
            event_date         date,
            enrichment_status  text NOT NULL DEFAULT 'pending',
            llm_model          text,
            prompt_version     text,
            first_seen_at      timestamptz NOT NULL DEFAULT now(),
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT articles_title_not_blank CHECK (btrim(title) <> ''),
            CONSTRAINT articles_url_web CHECK (url_canonical ~ '^https?://'),
            CONSTRAINT articles_extraction_known
                CHECK (extraction_status IN ('pending', 'ok', 'fallback')),
            CONSTRAINT articles_enrichment_known
                CHECK (enrichment_status IN ('pending', 'ok', 'failed', 'skipped'))
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX articles_url_hash_key ON articles (url_hash)")
    op.execute("CREATE INDEX articles_published_id ON articles (published_at, id)")
    op.execute("CREATE INDEX articles_title_trgm ON articles USING gin (title_norm gin_trgm_ops)")
    op.execute("CREATE INDEX articles_text_hash ON articles (text_hash)")
    op.execute(
        """
        CREATE TABLE article_texts (
            article_id    bigint PRIMARY KEY REFERENCES articles (id) ON DELETE CASCADE,
            body          text NOT NULL,
            extracted_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX article_texts_extracted ON article_texts (extracted_at)")
    op.execute(
        """
        CREATE TABLE article_concepts (
            article_id        bigint NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
            concept_id        bigint NOT NULL REFERENCES concepts (id),
            is_relevant       boolean NOT NULL,
            relevance_score   real NOT NULL,
            relevance_reason  text,
            PRIMARY KEY (article_id, concept_id),
            CONSTRAINT article_concepts_score_range
                CHECK (relevance_score >= 0 AND relevance_score <= 1)
        )
        """
    )
    op.execute("CREATE INDEX article_concepts_concept ON article_concepts (concept_id)")
    op.execute(
        """
        CREATE TABLE article_locations (
            id            bigserial PRIMARY KEY,
            article_id    bigint NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
            mention_text  text NOT NULL,
            role          text NOT NULL,
            -- Nulo si la mención no se pudo resolver (ambigua o desconocida).
            region_id     bigint REFERENCES regions (id),
            precision     text NOT NULL,
            confidence    real NOT NULL,
            is_primary    boolean NOT NULL DEFAULT false,
            -- Del catálogo (localidad o centroide), nunca de la IA (§11).
            point         geometry(Point, 4326),
            CONSTRAINT article_locations_role_known CHECK (role IN ('event', 'mentioned')),
            CONSTRAINT article_locations_precision_known CHECK (
                precision IN ('country', 'state', 'municipality', 'locality', 'unknown')
            ),
            CONSTRAINT article_locations_confidence_range
                CHECK (confidence >= 0 AND confidence <= 1)
        )
        """
    )
    op.execute("CREATE INDEX article_locations_article ON article_locations (article_id)")
    op.execute("CREATE INDEX article_locations_region ON article_locations (region_id)")
    op.execute("CREATE INDEX article_locations_point ON article_locations USING gist (point)")
    # Una sola ubicación principal por nota.
    op.execute(
        "CREATE UNIQUE INDEX article_locations_one_primary "
        "ON article_locations (article_id) WHERE is_primary"
    )
    op.execute(
        """
        CREATE TABLE search_results (
            search_id      uuid NOT NULL REFERENCES searches (id) ON DELETE CASCADE,
            article_id     bigint NOT NULL REFERENCES articles (id),
            provider       text NOT NULL,
            provider_rank  integer NOT NULL,
            in_region      boolean,
            PRIMARY KEY (search_id, article_id, provider),
            CONSTRAINT search_results_rank_positive CHECK (provider_rank >= 1)
        )
        """
    )
    op.execute("CREATE INDEX search_results_article ON search_results (article_id)")


def downgrade() -> None:
    """Elimina las tablas (se pierden las notas procesadas)."""
    op.execute("DROP TABLE search_results")
    op.execute("DROP TABLE article_locations")
    op.execute("DROP TABLE article_concepts")
    op.execute("DROP TABLE article_texts")
    op.execute("DROP TABLE articles")
