"""Borrar personas del monitor (borrado lógico, 10/11/2026, ADR-0043).

Benji pidió poder borrar usuarios desde «Accesos». Se borran de forma
lógica (``users.deleted_at``), como los conceptos:

- la persona desaparece de la lista y ya no puede entrar: se le quitan
  contraseña, código de 6 dígitos y llaves, y se cierran sus sesiones;
- su **usuario queda reservado**. Las búsquedas y casos guardan el usuario
  como texto: si alguien nuevo se llamara igual, la seguridad por filas le
  mostraría lo de la persona borrada. Así no puede pasar;
- la bitácora conserva todo lo que hizo.

Sin índice: la tabla es chica y se filtra junto con ``id`` o ``username``,
que ya están indexados.

Revisión: 0041
Anterior: 0040
Fecha: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega ``users.deleted_at``."""
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Quita ``users.deleted_at`` (las personas borradas vuelven a la lista, desactivadas)."""
    op.drop_column("users", "deleted_at")
