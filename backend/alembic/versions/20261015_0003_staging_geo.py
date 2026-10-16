"""Crear el esquema staging_geo para el pipeline de geodatos.

Es el área de trabajo de ``make geo-load``: ``ogr2ogr`` deja ahí cada capa
tal como viene (ya reproyectada a EPSG:4326) y el cargador la transforma
hacia ``regions``. Las tablas de este esquema son temporales: las crea y
las borra el propio cargador en cada corrida. Lo que vive aquí no es parte
del modelo de datos de la aplicación y la API nunca lo lee.

Se crea con una migración porque CLAUDE.md §6.3 exige que todo cambio de
esquema pase por Alembic.

Revisión: 0003
Anterior: 0002
Fecha: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea el esquema de trabajo del pipeline de geodatos."""
    op.execute("CREATE SCHEMA IF NOT EXISTS staging_geo")


def downgrade() -> None:
    """Elimina el esquema de trabajo y cualquier tabla temporal que quede."""
    op.execute("DROP SCHEMA IF EXISTS staging_geo CASCADE")
