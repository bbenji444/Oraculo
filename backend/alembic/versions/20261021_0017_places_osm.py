"""Colonias de OpenStreetMap y dos columnas nuevas de ubicación (ADR-0020).

INEGI no tiene colonias, y las notas dicen "Polanco", "Roma Norte" o "Santa
Cruz Meyehualco". La tabla ``places`` guarda las colonias, barrios y zonas de
OpenStreetMap que trae el mapa base ya descargado (capa ``places`` de
``basemap_mexico.pmtiles``), cada una con su punto y el municipio de INEGI que
la contiene. La carga es ``make geo-places``.

- ``name_core``: nombre normalizado sin la palabra genérica ("COLONIA ROMA
  NORTE" → "ROMA NORTE"). Con él se busca, exacto o como inicio de palabra
  ("POLANCO" encuentra "POLANCO 1ª SECCION").
- ``article_locations.place_name``: la colonia que se usó ("Colonia Polanco 1ª
  Sección"), para mostrarla junto al municipio.
- ``article_locations.municipality_hint``: el municipio que dice la IA para una
  colonia o calle (prompt ``enrich_v2``).

Índices en la misma migración (CLAUDE.md §6.3): búsqueda por ``name_core``
(igualdad y prefijo con ``text_pattern_ops``) y por municipio.

Revisión: 0017
Anterior: 0016
Fecha: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea ``places`` y agrega las columnas de ubicación."""
    op.execute(
        """
        CREATE TABLE places (
            id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name             text NOT NULL,
            name_core        text NOT NULL,
            kind             text NOT NULL,
            kind_detail      text,
            municipality_id  bigint NOT NULL REFERENCES regions (id) ON DELETE CASCADE,
            point            geometry(Point, 4326) NOT NULL,
            wikidata         text,
            source           text NOT NULL,
            CONSTRAINT places_kind_known
                CHECK (kind IN ('neighbourhood', 'macrohood', 'locality')),
            CONSTRAINT places_name_not_blank CHECK (btrim(name_core) <> '')
        )
        """
    )
    op.execute("CREATE INDEX places_name_core ON places (name_core text_pattern_ops)")
    op.execute("CREATE INDEX places_municipality ON places (municipality_id)")
    op.execute(
        """
        ALTER TABLE article_locations
            ADD COLUMN place_name text,
            ADD COLUMN municipality_hint text
        """
    )


def downgrade() -> None:
    """Quita la tabla y las columnas (se recargan con ``make geo-places``)."""
    op.execute(
        "ALTER TABLE article_locations DROP COLUMN place_name, DROP COLUMN municipality_hint"
    )
    op.execute("DROP TABLE places")
