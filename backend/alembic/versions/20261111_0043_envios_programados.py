"""Envíos programados: cada quien sus reportes, horas y días (11/11/2026, ADR-0046).

Benji: «que los envíos sean totalmente moldeables y personalizables», para
los usuarios y para él. Cada envío programado dice qué temas, de qué región,
a qué horas, qué días y a qué correos de su dueño.

Cambios:

- ``delivery_schedules``: los envíos programados, con dueño y seguridad por
  filas (cada quien ve los suyos; el superusuario y el worker, todos).
- ``delivery_schedule_recipients``: a qué correos va cada envío.
- ``delivery_schedule_claims``: corridas ya apartadas por el reloj, para no
  lanzar dos veces la misma (temas + región + periodo).
- ``searches.topic_key``: qué buscó una corrida automática; el reporte busca
  la anterior **del mismo tema** para separar lo nuevo. Se llena para las
  corridas que ya existían.
- Datos: el horario único de hoy pasa a ser el envío «Monitor FGR» de Benji,
  con sus correos. Cada usuario que ya existe recibe una copia con sus
  correos (si no los tiene, no se corre nada hasta que agregue uno).

``monitor_schedule`` se queda como estaba, ya sin uso: se borra en otra
migración, con permiso de Benji.

Índices: ``owner`` (se filtra por él), los envíos prendidos (los lee el reloj
cada minuto) y ``(topic_key, created_at)`` de las corridas automáticas.

Revisión: 0043
Anterior: 0042
Fecha: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OWN = "app_privileged() OR owner = app_username()"
_BY_SCHEDULE = (
    "app_privileged() OR EXISTS (SELECT 1 FROM delivery_schedules s "
    "WHERE s.id = delivery_schedule_recipients.schedule_id)"
)
# Lo mismo que AUTOMATIC_CONCEPT, AUTOMATIC_REGION_CODE y AUTOMATIC_RUN_HOURS
# por omisión (app/core/config.py): el monitor FGR de siempre.
_FGR_NAME_NORM = "FISCALIA GENERAL DE LA REPUBLICA"
_MEXICO_CODE = "MEX"
_FGR_TIMES = "'{420,900,1380}'::smallint[]"


def _rls(table: str, condition: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_owner ON {table} USING ({condition}) WITH CHECK ({condition})"
    )


def upgrade() -> None:
    """Crea los envíos programados y pasa el horario de hoy a envíos de cada persona."""
    op.create_table(
        "delivery_schedules",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("concept_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("region_id", sa.BigInteger(), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("times", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column(
            "days",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default=sa.text("'{}'::smallint[]"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("cardinality(times) > 0", name="delivery_schedules_has_times"),
        sa.CheckConstraint("cardinality(concept_ids) > 0", name="delivery_schedules_has_concepts"),
    )
    op.create_index("delivery_schedules_owner", "delivery_schedules", ["owner", "id"])
    op.create_index(
        "delivery_schedules_active",
        "delivery_schedules",
        ["id"],
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "delivery_schedule_recipients",
        sa.Column(
            "schedule_id",
            sa.BigInteger(),
            sa.ForeignKey("delivery_schedules.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "recipient_id",
            sa.BigInteger(),
            sa.ForeignKey("delivery_recipients.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    # Para borrar un correo y encontrar sus envíos (la llave primaria empieza
    # por schedule_id).
    op.create_index(
        "delivery_schedule_recipients_recipient",
        "delivery_schedule_recipients",
        ["recipient_id"],
    )
    op.create_table(
        "delivery_schedule_claims",
        sa.Column("run_key", sa.Text(), primary_key=True),
        sa.Column(
            "claimed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column("searches", sa.Column("topic_key", sa.Text(), nullable=True))
    op.create_index(
        "searches_topic_created",
        "searches",
        ["topic_key", "created_at"],
        postgresql_where=sa.text("trigger = 'automatic'"),
    )
    op.execute(
        """
        UPDATE searches s SET topic_key = t.key
        FROM (
            SELECT sc.search_id,
                   'c=' || string_agg(sc.concept_id::text, ',' ORDER BY sc.concept_id)
                   || '|r=' || max(s2.region_id)::text AS key
            FROM search_concepts sc JOIN searches s2 ON s2.id = sc.search_id
            WHERE s2.trigger = 'automatic'
            GROUP BY sc.search_id
        ) t
        WHERE s.id = t.search_id
        """
    )
    _rls("delivery_schedules", _OWN)
    _rls("delivery_schedule_recipients", _BY_SCHEDULE)
    _seed_fgr_schedules()


def _seed_fgr_schedules() -> None:
    """El monitor FGR de hoy, como un envío de cada persona (sin FGR o sin México, nada)."""
    op.execute(
        f"""
        WITH fgr AS (
            SELECT
                (SELECT id FROM concepts WHERE name_norm = '{_FGR_NAME_NORM}'
                 AND deleted_at IS NULL ORDER BY id LIMIT 1) AS concept_id,
                (SELECT id FROM regions WHERE code = '{_MEXICO_CODE}' ORDER BY id LIMIT 1)
                    AS region_id,
                COALESCE((SELECT times FROM monitor_schedule WHERE id = 1), {_FGR_TIMES})
                    AS times,
                COALESCE((SELECT days FROM monitor_schedule WHERE id = 1),
                         '{{}}'::smallint[]) AS days
        ),
        owners AS (
            SELECT username FROM users WHERE deleted_at IS NULL
            UNION SELECT DISTINCT owner FROM delivery_recipients
        )
        INSERT INTO delivery_schedules (owner, name, concept_ids, region_id, times, days)
        SELECT o.username, 'Monitor FGR', ARRAY[f.concept_id], f.region_id, f.times, f.days
        FROM owners o CROSS JOIN fgr f
        WHERE f.concept_id IS NOT NULL AND f.region_id IS NOT NULL
        """  # noqa: S608 — solo constantes de esta migración, ningún dato de nadie
    )
    op.execute(
        """
        INSERT INTO delivery_schedule_recipients (schedule_id, recipient_id)
        SELECT s.id, r.id FROM delivery_schedules s
        JOIN delivery_recipients r ON r.owner = s.owner AND r.is_active
        """
    )


def downgrade() -> None:
    """Quita los envíos programados (el horario único sigue en monitor_schedule)."""
    for table in ("delivery_schedule_recipients", "delivery_schedules"):
        op.execute(f"DROP POLICY {table}_owner ON {table}")
    op.drop_index("searches_topic_created", table_name="searches")
    op.drop_column("searches", "topic_key")
    op.drop_table("delivery_schedule_claims")
    op.drop_table("delivery_schedule_recipients")
    op.drop_table("delivery_schedules")
