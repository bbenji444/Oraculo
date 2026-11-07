"""Horario único de las corridas y envíos para todos (06/11/2026, ADR-0040).

Benji: la sección «Envíos» es solo para el administrador. Hay un solo
horario para todos; si se agrega, cambia o quita una hora, aplica a todos, y
a cada hora se hace una corrida nueva. Nada por usuario: cada horario
distinto sería otra corrida y más tokens.

Cambios:

- ``monitor_schedule``: el horario (una sola fila, ``id = 1``). ``times`` son
  minutos del día (07:00 = 420) y ``days`` días ISO (vacío = todos). Sin fila,
  vale ``AUTOMATIC_RUN_HOURS`` del ``.env``.
- ``monitor_schedule_claims``: qué hora programada ya se lanzó. El reloj
  revisa cada minuto; la llave primaria impide lanzar dos veces la misma
  corrida aunque el worker tarde en tomarla.
- ``delivery_rules`` queda como «cómo se manda cada fuente»: canal, cuenta y
  si está prendida. Se borran las reglas personalizadas (``audience =
  'selected'``, aprobado por Benji el 06/11/2026) y las columnas de horas,
  días y destinatarios. Queda una regla por fuente y canal (índice único
  ``delivery_rules_source_channel``). Los envíos pasados se conservan: su
  ``rule_id`` queda vacío (``ON DELETE SET NULL``).

Índices: las dos tablas nuevas se leen por llave primaria.

Revisión: 0037
Anterior: 0036
Fecha: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DROPPED = ("days", "times", "exclude_ids", "recipient_ids", "audience", "name")


def upgrade() -> None:
    """Crea el horario único y deja una regla de envío por fuente y canal."""
    op.create_table(
        "monitor_schedule",
        sa.Column("id", sa.SmallInteger(), primary_key=True, server_default="1"),
        sa.Column("times", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column(
            "days",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default=sa.text("'{}'::smallint[]"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="monitor_schedule_single_row"),
        sa.CheckConstraint("cardinality(times) > 0", name="monitor_schedule_has_times"),
    )
    op.create_table(
        "monitor_schedule_claims",
        sa.Column("slot", sa.DateTime(timezone=True), primary_key=True),
        sa.Column(
            "claimed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute("DELETE FROM delivery_rules WHERE audience = 'selected'")
    # Si quedaron varias reglas «para todos» de la misma fuente y canal, se
    # conserva la más vieja.
    op.execute(
        "DELETE FROM delivery_rules r USING delivery_rules o "
        "WHERE r.source = o.source AND r.channel = o.channel AND r.id > o.id"
    )
    op.drop_constraint("delivery_rules_audience", "delivery_rules")
    for column in _DROPPED:
        op.drop_column("delivery_rules", column)
    op.create_index(
        "delivery_rules_source_channel", "delivery_rules", ["source", "channel"], unique=True
    )


def downgrade() -> None:
    """Vuelve a las reglas abiertas (sin horario único); el horario guardado se pierde."""
    op.drop_index("delivery_rules_source_channel", table_name="delivery_rules")
    op.add_column(
        "delivery_rules", sa.Column("name", sa.Text(), nullable=False, server_default="Regla")
    )
    op.add_column(
        "delivery_rules", sa.Column("audience", sa.Text(), nullable=False, server_default="all")
    )
    for column, kind, default in (
        ("recipient_ids", sa.BigInteger(), "'{}'::bigint[]"),
        ("exclude_ids", sa.BigInteger(), "'{}'::bigint[]"),
        ("times", sa.SmallInteger(), "'{420,900,1380}'::smallint[]"),
        ("days", sa.SmallInteger(), "'{}'::smallint[]"),
    ):
        op.add_column(
            "delivery_rules",
            sa.Column(
                column, postgresql.ARRAY(kind), nullable=False, server_default=sa.text(default)
            ),
        )
    op.create_check_constraint(
        "delivery_rules_audience", "delivery_rules", "audience IN ('all', 'selected')"
    )
    op.drop_table("monitor_schedule_claims")
    op.drop_table("monitor_schedule")
