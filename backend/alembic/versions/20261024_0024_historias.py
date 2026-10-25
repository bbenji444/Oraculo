"""Historias: notas del mismo hecho en varios medios (F12.1c, ADR-0026).

- ``articles.story_id``: id de la primera nota de su historia. ``NULL`` si
  la nota está sola. No se borra nada: deshacer una historia es poner
  ``NULL``. Si se borra la primera nota, las demás quedan solas (``SET NULL``)
  y ``make agrupar-historias`` las vuelve a juntar.

Índice en la misma migración (CLAUDE.md §6.3): la lista de resultados y el
reporte agrupan por ``story_id``.

Revisión: 0024
Anterior: 0023
Fecha: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega la columna y su índice."""
    op.execute(
        "ALTER TABLE articles ADD COLUMN story_id bigint "
        "REFERENCES articles (id) ON DELETE SET NULL"
    )
    op.execute("CREATE INDEX articles_story ON articles (story_id) WHERE story_id IS NOT NULL")


def downgrade() -> None:
    """Quita el índice y la columna."""
    op.execute("DROP INDEX articles_story")
    op.execute("ALTER TABLE articles DROP COLUMN story_id")
