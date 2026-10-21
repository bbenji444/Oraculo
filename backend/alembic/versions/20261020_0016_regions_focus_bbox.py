"""Columna ``regions.focus_bbox``: el encuadre de la parte principal.

El ``bbox`` de un país incluye todos sus territorios: el de Francia va de
Guadalupe (-61°) a Reunión (55°) y el de Estados Unidos o Rusia cruza el
meridiano 180, así que cubre el mundo. Al elegirlos, el globo se alejaba en
lugar de acercarse. ``focus_bbox`` guarda el rectángulo de la parte principal
(Francia continental con Córcega, Estados Unidos contiguo) y el globo
encuadra con él. ``NULL`` = la región es de una sola parte y su encuadre es el
``bbox``.

No se indexa: nunca se filtra ni se ordena por esta columna.

La consulta es una copia congelada de ``FILL_FOCUS_BBOX_SQL`` en
``app/geodata/carga.py`` (las migraciones no importan código de la app, para
que no cambien si la app cambia). La carga de geodatos la recalcula.

Revisión: 0016
Anterior: 0015
Fecha: 2026-10-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mismos valores que app/geodata/carga.py (ver su comentario).
_FILL = """
WITH parts AS (
    SELECT r.id, d.geom AS g
    FROM regions r, LATERAL ST_Dump(r.geom) AS d
    WHERE r.geom IS NOT NULL AND ST_NumGeometries(r.geom) > 1
), clustered AS (
    SELECT id, g, ST_Area(g::geography) AS area,
           ST_ClusterDBSCAN(ST_Simplify(g, 0.1), eps := 2.0, minpoints := 1)
               OVER (PARTITION BY id) AS cid
    FROM parts
), clusters AS (
    SELECT id, cid, sum(area) AS area, max(area) AS biggest_part, ST_Extent(g)::geometry AS box
    FROM clustered GROUP BY id, cid
), ranked AS (
    SELECT *, sum(area) OVER (PARTITION BY id) AS total,
           max(biggest_part) OVER (PARTITION BY id) AS region_biggest
    FROM clusters
), kept AS (
    SELECT id, ST_Extent(box)::geometry AS box
    FROM ranked
    WHERE biggest_part = region_biggest OR area >= 0.25 * total
    GROUP BY id
)
UPDATE regions r
SET focus_bbox = ARRAY[ST_XMin(k.box), ST_YMin(k.box), ST_XMax(k.box), ST_YMax(k.box)]
FROM kept k
WHERE k.id = r.id
"""


def upgrade() -> None:
    """Agrega la columna y la llena para las regiones ya cargadas."""
    op.execute(
        """
        ALTER TABLE regions
            ADD COLUMN focus_bbox double precision[],
            ADD CONSTRAINT regions_focus_bbox_four_values
                CHECK (focus_bbox IS NULL OR cardinality(focus_bbox) = 4)
        """
    )
    op.execute(_FILL)


def downgrade() -> None:
    """Quita la columna (se puede recalcular desde la geometría)."""
    op.execute("ALTER TABLE regions DROP COLUMN focus_bbox")
