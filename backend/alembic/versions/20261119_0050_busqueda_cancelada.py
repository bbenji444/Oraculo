"""Búsqueda cancelada: el estado ``cancelled`` (19/11/2026, ADR-0118).

Benji: «tiene que estar la opción de cancelar búsqueda por si me equivoqué en
algo o necesito regresar y editar». Quien lanzó una búsqueda manual la puede
detener mientras corre; se queda lo que alcanzó a encontrar y lo gastado.

Solo amplía la regla ``searches_status_known`` con ``cancelled``: ninguna fila
cambia al subir. Sin índices nuevos: el historial ya filtra por dueño y fecha,
y el estado se lee junto con la búsqueda, que se busca por su id.

Bajar convierte las búsquedas canceladas en ``failed`` (con su resumen de error
intacto) para que la regla anterior las acepte: es un cambio de datos y por eso
no se hace sin respaldo (``make db-dump``).

Revisión: 0050
Anterior: 0049
Fecha: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "searches_status_known"
_BEFORE = "'pending', 'running', 'completed', 'partial', 'failed'"


def upgrade() -> None:
    """Acepta ``cancelled`` en ``searches.status``."""
    op.drop_constraint(_CONSTRAINT, "searches", type_="check")
    op.create_check_constraint(_CONSTRAINT, "searches", f"status IN ({_BEFORE}, 'cancelled')")


def downgrade() -> None:
    """Vuelve a la regla anterior; las canceladas quedan como ``failed``."""
    op.execute("UPDATE searches SET status = 'failed' WHERE status = 'cancelled'")
    op.drop_constraint(_CONSTRAINT, "searches", type_="check")
    op.create_check_constraint(_CONSTRAINT, "searches", f"status IN ({_BEFORE})")
