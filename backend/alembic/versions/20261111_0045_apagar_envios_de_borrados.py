"""Apagar los envíos programados de las personas ya borradas (11/11/2026).

En la VM, «pp» estaba borrada y su envío «Monitor FGR» seguía prendido. No
mandaba nada porque no tenía correos, pero con uno habría seguido mandando
reportes. Desde esta versión, borrar a una persona apaga sus envíos en la
misma transacción (``PostgresAccessStore.delete_user``); esta migración
apaga los que quedaron prendidos de antes.

Solo cambia ``is_active`` a ``false``: no borra envíos ni correos. Medido
antes de aplicarla: 0 en la base de desarrollo y 1 en la VM (el de «pp»).

Revisión: 0045
Anterior: 0044
Fecha: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apaga los envíos prendidos cuyo dueño está borrado."""
    op.execute(
        """
        UPDATE delivery_schedules SET is_active = false, updated_at = now()
        WHERE is_active
          AND owner IN (SELECT username FROM users WHERE deleted_at IS NOT NULL)
        """
    )


def downgrade() -> None:
    """No hace nada a propósito.

    Ya no se sabe cuáles estaban prendidos, y volver a prender los de personas
    borradas es justo lo que se quiso evitar.
    """
