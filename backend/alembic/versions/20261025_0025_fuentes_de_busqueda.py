"""Fuentes con las que se hizo cada búsqueda (F12.2, ADR-0027).

- ``searches.providers``: las fuentes que encendió el analista (``searchapi``,
  ``google_news_rss``, ``indice_local``…). ``'{}'`` en las búsquedas de antes
  de F12.2: usaron todas las configuradas, y así se siguen leyendo.

Sin índice: nunca se filtra ni se ordena por esta columna; se lee junto con
la búsqueda.

Revisión: 0025
Anterior: 0024
Fecha: 2026-10-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega la columna."""
    op.execute("ALTER TABLE searches ADD COLUMN providers text[] NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    """Quita la columna."""
    op.execute("ALTER TABLE searches DROP COLUMN providers")
