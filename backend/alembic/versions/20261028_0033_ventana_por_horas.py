"""Horas que cubre cada corrida automática (F12, 28/10/2026).

Antes cada corrida pedía «hoy y ayer» por días completos: la de las 07:00
volvía a traer todo lo del día anterior (de 160 relevantes, solo 23 eran
nuevas). Benji pidió que cada corrida cubra estrictamente desde la corrida
anterior: 23:00 a 07:00, 07:00 a 15:00 y 15:00 a 23:00.

Se guarda el inicio y el fin de esa ventana en la búsqueda, para filtrar las
notas por su hora de publicación y para decir en pantalla y en el PDF qué
horas cubre. Las búsquedas manuales y las corridas de antes quedan con las dos
columnas vacías: siguen por días, como siempre.

No se filtra ni se une por estas columnas: no llevan índice.

Revisión: 0033
Anterior: 0032
Fecha: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega el inicio y el fin de la ventana por horas."""
    op.add_column("searches", sa.Column("window_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("searches", sa.Column("window_end", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "searches_window_in_order",
        "searches",
        "(window_start IS NULL AND window_end IS NULL) OR window_start < window_end",
    )


def downgrade() -> None:
    """Quita la ventana por horas."""
    op.drop_constraint("searches_window_in_order", "searches", type_="check")
    op.drop_column("searches", "window_end")
    op.drop_column("searches", "window_start")
