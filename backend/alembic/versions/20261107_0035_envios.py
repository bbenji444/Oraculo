"""Envíos: cuentas, destinatarios, reglas y la guía de cada envío (07/11/2026, ADR-0039).

Benji pidió una sección «Envíos» donde administrar qué se manda, a quién, por
qué canal y a qué hora, pensada para volverse después un módulo general de
Oráculo. Por eso cada envío lleva una ``source`` (de dónde viene lo que se
manda: hoy ``monitor.corrida_fgr``) y una ``source_ref`` (cuál: el
``search_id`` de la corrida), y no depende de las tablas del monitor.

Tablas:

- ``delivery_accounts``: cuentas desde las que se manda (Outlook o Gmail vía
  Composio; WhatsApp más adelante). ``external_id`` es la cuenta conectada en
  Composio.
- ``delivery_recipients``: a quién se le manda.
- ``delivery_rules``: qué fuente, a quién, por qué canal, desde qué cuenta y en
  qué horas (``hours`` vacío = todas).
- ``deliveries``: la guía de cada envío (estado, intentos, error, número del
  proveedor). ``idempotency_key`` es único: la misma corrida nunca se manda dos
  veces al mismo destino por el mismo canal.
- ``delivery_attempts``: cada intento de cada envío, para rastrear fallas.

Índices: los de filtrar (``is_active``, ``status`` con ``next_attempt_at``,
``source``), unir (claves foráneas) y paginar el historial por cursor
(``created_at, id``), en esta misma migración (CLAUDE.md §6.3).

Revisión: 0035
Anterior: 0034
Fecha: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    ]


def upgrade() -> None:
    """Crea las tablas de envíos con sus índices."""
    op.create_table(
        "delivery_accounts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True, unique=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        *_timestamps(),
        sa.CheckConstraint(
            "provider IN ('outlook', 'gmail', 'whatsapp')", name="delivery_accounts_provider"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'failed', 'disabled')",
            name="delivery_accounts_status",
        ),
    )
    op.create_index("delivery_accounts_status_id", "delivery_accounts", ["status", "id"])

    op.create_table(
        "delivery_recipients",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.CheckConstraint("btrim(name) <> ''", name="delivery_recipients_name"),
        sa.CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL", name="delivery_recipients_contact"
        ),
    )
    op.create_index("delivery_recipients_active_id", "delivery_recipients", ["is_active", "id"])

    op.create_table(
        "delivery_rules",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "recipient_id",
            sa.BigInteger(),
            sa.ForeignKey("delivery_recipients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("delivery_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "hours",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default=sa.text("'{}'::smallint[]"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.CheckConstraint("channel IN ('email', 'whatsapp')", name="delivery_rules_channel"),
    )
    op.create_index("delivery_rules_source_active", "delivery_rules", ["source", "is_active"])
    op.create_index("delivery_rules_recipient", "delivery_rules", ["recipient_id"])
    op.create_index("delivery_rules_account", "delivery_rules", ["account_id"])

    op.create_table(
        "deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_id",
            sa.BigInteger(),
            sa.ForeignKey("delivery_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("delivery_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recipient_id",
            sa.BigInteger(),
            sa.ForeignKey("delivery_recipients.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("attachment_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider_ref", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("channel IN ('email', 'whatsapp')", name="deliveries_channel"),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'skipped')",
            name="deliveries_status",
        ),
    )
    op.create_index("deliveries_due", "deliveries", ["status", "next_attempt_at"])
    op.create_index("deliveries_history", "deliveries", [sa.text("created_at DESC"), "id"])
    op.create_index("deliveries_source_ref", "deliveries", ["source", "source_ref"])
    op.create_index("deliveries_rule", "deliveries", ["rule_id"])
    op.create_index("deliveries_account", "deliveries", ["account_id"])
    op.create_index("deliveries_recipient", "deliveries", ["recipient_id"])

    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "delivery_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deliveries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("provider_status", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("delivery_attempts_delivery", "delivery_attempts", ["delivery_id", "attempt"])


def downgrade() -> None:
    """Quita las tablas de envíos (borra su historial)."""
    op.drop_table("delivery_attempts")
    op.drop_table("deliveries")
    op.drop_table("delivery_rules")
    op.drop_table("delivery_recipients")
    op.drop_table("delivery_accounts")
