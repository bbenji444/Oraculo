"""Agregar términos de búsqueda y códigos de país a regions (ADR-0009).

- ``search_terms``: con qué palabras se busca el lugar en los proveedores de
  noticias. Vacío significa "usar ``name``". Lo llena ``make geo-terms``
  desde ``geodata/search_terms.csv``.
- ``iso_a2``, ``fips_code`` y ``name_en`` (solo países): los filtros por
  país de cada proveedor. SearchApi y Google News RSS usan ISO-2; GDELT usa
  FIPS y, si no existe, el nombre en inglés sin espacios.

Ninguna de estas columnas se usa para filtrar, unir ni paginar: se leen de
una región ya elegida por id, así que no llevan índice (CLAUDE.md §6.3).

Revisión: 0004
Anterior: 0003
Fecha: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega las columnas y sus restricciones."""
    op.execute(
        """
        ALTER TABLE regions
            ADD COLUMN search_terms text[] NOT NULL DEFAULT '{}',
            ADD COLUMN iso_a2 text,
            ADD COLUMN fips_code text,
            ADD COLUMN name_en text,
            -- Los códigos de país no tienen sentido en estados o municipios.
            ADD CONSTRAINT regions_country_codes_only_in_countries CHECK (
                level = 'country'
                OR (iso_a2 IS NULL AND fips_code IS NULL AND name_en IS NULL)
            ),
            -- Ambos son de 2 letras mayúsculas (ISO 3166-1 alfa-2 y FIPS 10-4).
            ADD CONSTRAINT regions_iso_a2_format CHECK (iso_a2 ~ '^[A-Z]{2}$'),
            ADD CONSTRAINT regions_fips_code_format CHECK (fips_code ~ '^[A-Z]{2}$')
        """
    )


def downgrade() -> None:
    """Quita las columnas (se pierden los términos y códigos cargados)."""
    op.execute(
        """
        ALTER TABLE regions
            DROP COLUMN search_terms,
            DROP COLUMN iso_a2,
            DROP COLUMN fips_code,
            DROP COLUMN name_en
        """
    )
