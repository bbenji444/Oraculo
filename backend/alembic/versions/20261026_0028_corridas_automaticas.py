"""Corridas automáticas del monitor FGR (F12.8, ADR-0031).

- ``searches.trigger``: ``manual`` (la pidió una persona) o ``automatic`` (la
  lanzó el reloj a las 07:00, 15:00 o 23:00). Las automáticas aparecen en el
  historial de todos los analistas.
- ``searches.scheduled_for``: la hora programada de la corrida (por ejemplo
  07:00 CDMX), para mostrar «Corrida de las 07:00» aunque haya empezado tarde.
- ``reports.pdf_path``: dónde quedó guardado el PDF que la corrida armó sola.

Índice en la misma migración (CLAUDE.md §6.3): las automáticas por fecha,
porque el historial y el monitor las piden de la más reciente a la más vieja.

Revisión: 0028
Anterior: 0027
Fecha: 2026-10-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega el tipo de búsqueda, su hora programada y la ruta del PDF."""
    op.execute(
        "ALTER TABLE searches "
        "ADD COLUMN trigger text NOT NULL DEFAULT 'manual' "
        "CHECK (trigger IN ('manual', 'automatic')), "
        "ADD COLUMN scheduled_for timestamptz"
    )
    op.execute(
        "CREATE INDEX searches_automatic ON searches (created_at DESC, id DESC) "
        "WHERE trigger = 'automatic'"
    )
    op.execute("ALTER TABLE reports ADD COLUMN pdf_path text")


def downgrade() -> None:
    """Quita la ruta del PDF, el índice y las columnas de la corrida."""
    op.execute("ALTER TABLE reports DROP COLUMN pdf_path")
    op.execute("DROP INDEX searches_automatic")
    op.execute("ALTER TABLE searches DROP COLUMN trigger, DROP COLUMN scheduled_for")
