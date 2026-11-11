"""Envíos por usuario: cada quien sus destinatarios y sus horas (11/11/2026, ADR-0045).

Benji: «que ellos agreguen su correo y ya les van a estar empezando a llegar
las noticias»; por ahora, de las corridas de la FGR a las horas de siempre.
El correo que envía (Ovitech) y el horario los maneja el superusuario.

Cambios:

- ``delivery_recipients.owner``: de quién es el destinatario (el ``username``).
  Los que ya existían quedan a nombre de ``benji``: todo lo de Benji sigue
  igual.
- ``delivery_recipients.hours``: a qué horas del horario quiere recibir
  (minutos del día, como ``monitor_schedule.times``); vacío = a todas.
- ``deliveries.owner``: de quién es cada envío, para que cada persona vea solo
  su historial. Los pasados toman el dueño de su destinatario.
- Seguridad por filas en las dos tablas: cada persona ve lo suyo; el
  superusuario y el sistema (worker) ven todo.

Índices: ``owner`` en las dos tablas (se filtra por él en cada lectura).

Revisión: 0042
Anterior: 0041
Fecha: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUPERUSER = "benji"
_OWN = "app_privileged() OR owner = app_username()"


def upgrade() -> None:
    """Agrega dueño y horas, pasa lo existente a Benji y enciende RLS."""
    op.add_column(
        "delivery_recipients",
        sa.Column("owner", sa.Text(), nullable=False, server_default=_SUPERUSER),
    )
    op.add_column(
        "delivery_recipients",
        sa.Column(
            "hours",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default=sa.text("'{}'::smallint[]"),
        ),
    )
    op.create_index("delivery_recipients_owner", "delivery_recipients", ["owner", "id"])
    op.add_column("deliveries", sa.Column("owner", sa.Text(), nullable=True))
    op.execute(
        "UPDATE deliveries d SET owner = COALESCE("
        "(SELECT r.owner FROM delivery_recipients r WHERE r.id = d.recipient_id), "
        "'benji')"  # el superusuario de la migración 0038
    )
    op.alter_column("deliveries", "owner", nullable=False, server_default=_SUPERUSER)
    op.create_index("deliveries_owner_created", "deliveries", ["owner", "created_at"])
    for table in ("delivery_recipients", "deliveries"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_owner ON {table} USING ({_OWN}) WITH CHECK ({_OWN})")


def downgrade() -> None:
    """Apaga RLS y quita las columnas."""
    for table in ("delivery_recipients", "deliveries"):
        op.execute(f"DROP POLICY {table}_owner ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("deliveries_owner_created", table_name="deliveries")
    op.drop_column("deliveries", "owner")
    op.drop_index("delivery_recipients_owner", table_name="delivery_recipients")
    op.drop_column("delivery_recipients", "hours")
    op.drop_column("delivery_recipients", "owner")
