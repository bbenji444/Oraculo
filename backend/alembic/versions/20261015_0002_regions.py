"""Crear la tabla regions: catálogo geográfico unificado.

Un solo catálogo para países, estados, municipios/alcaldías y localidades
(ADR-0002), con las claves INEGI en ``code`` para México y el ISO-A3 para
otros países. Todas las columnas que se usan para filtrar, buscar, unir o
paginar llevan su índice en esta misma migración (CLAUDE.md §6.3).

Columnas según la especificación §6 y v1.1 (``aliases``), más ``source``
para saber de qué edición de qué fuente viene cada fila (ADR-0008).

Revisión: 0002
Anterior: 0001
Fecha: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea el tipo region_level, la tabla regions, sus índices y su disparador."""
    op.execute("CREATE TYPE region_level AS ENUM ('country', 'state', 'municipality', 'locality')")
    op.execute(
        """
        CREATE TABLE regions (
            id              bigserial PRIMARY KEY,
            level           region_level NOT NULL,
            -- Clave INEGI (CVEGEO: '09', '09007', '090070001') o ISO-A3 ('COL').
            code            text NOT NULL,
            parent_id       bigint REFERENCES regions (id) ON DELETE RESTRICT,
            country_code    text NOT NULL,
            -- Nombre original, con acentos, para mostrar.
            name            text NOT NULL,
            -- Nombre para comparar: app.domain.names.normalize_name (conserva la Ñ).
            name_norm       text NOT NULL,
            aliases         text[] NOT NULL DEFAULT '{}',
            aliases_norm    text[] NOT NULL DEFAULT '{}',
            -- 'Alcaldía', 'Municipio', 'Estado'... para mostrar "Alcaldía Iztapalapa".
            display_prefix  text NOT NULL,
            -- Resolución completa; nulo solo en localidades rurales puntuales.
            geom            geometry(MultiPolygon, 4326),
            -- Punto representativo (ST_PointOnSurface, siempre dentro de geom).
            centroid        geometry(Point, 4326) NOT NULL,
            -- [oeste, sur, este, norte] en grados, listo para fitBounds de MapLibre.
            bbox            double precision[] NOT NULL,
            population      integer,
            -- Fuente y edición, por ejemplo 'INEGI MG Encuesta Intercensal 2025'.
            source          text NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT regions_code_key UNIQUE (code),
            CONSTRAINT regions_bbox_four_values CHECK (cardinality(bbox) = 4),
            CONSTRAINT regions_country_without_parent
                CHECK (level <> 'country' OR parent_id IS NULL),
            CONSTRAINT regions_only_localities_without_geom
                CHECK (geom IS NOT NULL OR level = 'locality'),
            CONSTRAINT regions_population_not_negative
                CHECK (population IS NULL OR population >= 0)
        )
        """
    )

    # Consultas espaciales: "¿en qué región cae este punto?" y cercanía.
    op.execute("CREATE INDEX regions_geom_gist ON regions USING gist (geom)")
    op.execute("CREATE INDEX regions_centroid_gist ON regions USING gist (centroid)")
    # Búsqueda difusa por nombre ("izta" → Iztapalapa) y búsqueda por alias.
    op.execute("CREATE INDEX regions_name_norm_trgm ON regions USING gin (name_norm gin_trgm_ops)")
    op.execute("CREATE INDEX regions_aliases_norm_gin ON regions USING gin (aliases_norm)")
    # Jerarquía: hijos de una región y filtros por nivel.
    op.execute("CREATE INDEX regions_level_parent ON regions (level, parent_id)")
    # Pertenencia por prefijo de clave INEGI ('09007' LIKE '09%'), ADR-0002.
    op.execute("CREATE INDEX regions_code_prefix ON regions (code text_pattern_ops)")
    # Paginación alfabética por cursor (name_norm, id), nunca OFFSET.
    op.execute("CREATE INDEX regions_level_name_id ON regions (level, name_norm, id)")
    op.execute("CREATE INDEX regions_parent_name_id ON regions (parent_id, name_norm, id)")

    # updated_at se mantiene solo: lo usará cualquier tabla futura que lo necesite.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER regions_set_updated_at BEFORE UPDATE ON regions "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    """Elimina la tabla regions y lo que se creó con ella (borra sus datos)."""
    op.execute("DROP TABLE regions")
    op.execute("DROP FUNCTION set_updated_at()")
    op.execute("DROP TYPE region_level")
