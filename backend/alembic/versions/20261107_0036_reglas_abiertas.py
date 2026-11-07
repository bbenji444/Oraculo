"""Reglas de envío abiertas: regla general, horas libres, días y excepciones (07/11/2026).

Benji vio el prototipo de «Envíos» y pidió reglas más abiertas:

- una regla general «a todos los destinatarios» (y, si quiere, «todos menos
  Tadeo»), en lugar de una regla por persona;
- poder agregar o quitar horas libremente (07:00, 15:00, 23:00 o 09:30) y
  elegir días de la semana;
- reglas personalizadas para unas cuantas personas.

Cambios en ``delivery_rules``:

- ``name``: nombre de la regla;
- ``audience``: ``all`` (todos los destinatarios activos) o ``selected``;
- ``recipient_ids`` (los elegidos) y ``exclude_ids`` (las excepciones de «todos»);
- ``times``: minutos del día (09:30 = 570) en lugar de ``hours``;
- ``days``: días ISO (1 = lunes … 7 = domingo); vacío = todos.

Las reglas que ya había se convierten sin perder nada: su destinatario pasa a
``recipient_ids`` y sus horas a ``times``. ``deliveries`` gana
``scheduled_for``: a qué hora programada respondió el envío.

Índices: ninguno nuevo. Las reglas son pocas y se leen todas por fuente
(índice ``delivery_rules_source_active``); ``scheduled_for`` solo se muestra.

Revisión: 0036
Anterior: 0035
Fecha: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _array(name: str, kind: type[sa.types.TypeEngine[int]], empty: str) -> sa.Column[object]:
    return sa.Column(
        name, postgresql.ARRAY(kind), nullable=False, server_default=sa.text(f"'{{}}'::{empty}")
    )


def upgrade() -> None:
    """Abre las reglas y convierte las existentes."""
    op.add_column(
        "delivery_rules", sa.Column("name", sa.Text(), nullable=False, server_default="Regla")
    )
    op.add_column(
        "delivery_rules",
        sa.Column("audience", sa.Text(), nullable=False, server_default="selected"),
    )
    op.add_column("delivery_rules", _array("recipient_ids", sa.BigInteger, "bigint[]"))
    op.add_column("delivery_rules", _array("exclude_ids", sa.BigInteger, "bigint[]"))
    op.add_column("delivery_rules", _array("times", sa.SmallInteger, "smallint[]"))
    op.add_column("delivery_rules", _array("days", sa.SmallInteger, "smallint[]"))
    # Una regla sin horas significaba «todas las corridas» (07:00, 15:00 y 23:00).
    op.execute(
        "UPDATE delivery_rules SET recipient_ids = ARRAY[recipient_id], "
        "times = CASE WHEN cardinality(hours) = 0 THEN ARRAY[420, 900, 1380]::smallint[] "
        "ELSE ARRAY(SELECT (h * 60)::smallint FROM unnest(hours) AS h ORDER BY h) END"
    )
    op.create_check_constraint(
        "delivery_rules_audience", "delivery_rules", "audience IN ('all', 'selected')"
    )
    op.drop_index("delivery_rules_recipient", table_name="delivery_rules")
    op.drop_column("delivery_rules", "recipient_id")
    op.drop_column("delivery_rules", "hours")
    op.add_column(
        "deliveries", sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Vuelve a una regla por persona; las reglas «para todos» se pierden."""
    op.drop_column("deliveries", "scheduled_for")
    op.add_column(
        "delivery_rules",
        sa.Column(
            "hours",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default=sa.text("'{}'::smallint[]"),
        ),
    )
    op.add_column("delivery_rules", sa.Column("recipient_id", sa.BigInteger(), nullable=True))
    op.execute("DELETE FROM delivery_rules WHERE cardinality(recipient_ids) = 0")
    op.execute(
        "UPDATE delivery_rules SET recipient_id = recipient_ids[1], "
        "hours = ARRAY(SELECT DISTINCT (t / 60)::smallint FROM unnest(times) AS t)"
    )
    op.alter_column("delivery_rules", "recipient_id", nullable=False)
    op.create_foreign_key(
        "delivery_rules_recipient_id_fkey",
        "delivery_rules",
        "delivery_recipients",
        ["recipient_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("delivery_rules_recipient", "delivery_rules", ["recipient_id"])
    op.drop_constraint("delivery_rules_audience", "delivery_rules")
    for column in ("days", "times", "exclude_ids", "recipient_ids", "audience", "name"):
        op.drop_column("delivery_rules", column)
