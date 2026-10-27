"""Eliminar casos y búsquedas sin perderlos (F12, 27/10/2026).

Benji pidió poder eliminar casos y quitar búsquedas del historial. Se borran
de forma reversible: ``deleted_at`` y ``deleted_by`` dicen cuándo y quién, y
la fila se queda (con sus notas, entidades y bitácora). Así un clic
equivocado se deshace y la auditoría no pierde nada (CLAUDE.md §8).

- ``cases.deleted_at`` / ``cases.deleted_by``: un caso eliminado ya no se ve
  en ninguna parte (lista, detalle, muro, globo).
- ``searches.deleted_at`` / ``searches.deleted_by``: una búsqueda eliminada
  sale del historial y de «la última corrida». Sus notas siguen en el índice
  y en los casos donde se agregaron.

Índices en la misma migración (CLAUDE.md §6.3): las listas solo piden filas
vivas, así que cada una tiene un índice parcial con su orden.

Bajarla quita las columnas: lo eliminado vuelve a verse.

Revisión: 0030
Anterior: 0029
Fecha: 2026-10-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega quién y cuándo eliminó, y los índices de las filas vivas."""
    for table in ("cases", "searches"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN deleted_at timestamptz, ADD COLUMN deleted_by text"
        )
    # Mis casos, del más reciente al más viejo (ListCases pagina así).
    op.execute(
        "CREATE INDEX cases_live_updated ON cases (updated_at DESC, id DESC) "
        "WHERE deleted_at IS NULL"
    )
    # El historial, de la más reciente a la más vieja.
    op.execute(
        "CREATE INDEX searches_live_created ON searches (created_at DESC, id DESC) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    """Quita los índices y las columnas."""
    op.execute("DROP INDEX IF EXISTS searches_live_created")
    op.execute("DROP INDEX IF EXISTS cases_live_updated")
    for table in ("searches", "cases"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN deleted_by, DROP COLUMN deleted_at")
