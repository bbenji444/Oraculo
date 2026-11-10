"""Personas y llaves de acceso del monitor (piloto, 10/11/2026, ADR-0042).

Benji pidió entrar con un «token» como el de la API de ChatGPT y que el
monitor sea multiusuario: cada quien con su historial.

- ``users``: cada persona. ``username`` es el identificador que ya guardan
  búsquedas, casos, conceptos y bitácora (texto). ``role`` es ``superuser`` o
  ``user``.
- ``access_keys``: las llaves de cada persona. Solo se guarda su huella
  (``key_hash``, HMAC-SHA256 con la pimienta del ``.env``) y su parte pública
  (``key_prefix``) para identificarla; nunca la llave completa. Se pueden
  revocar (``revoked_at``) o vencer (``expires_at``).
- Se crea el superusuario ``benji`` y lo que hoy es del usuario fijo de
  desarrollo («desarrollo») pasa a su nombre, tal cual pidió Benji. La
  bitácora (``audit_log``) no se reescribe: es el registro histórico.

Índices: ``users.username`` y ``access_keys.key_prefix`` únicos (se buscan
al entrar); ``access_keys.user_id`` (las llaves de cada persona).

Revisión: 0038
Anterior: 0037
Fecha: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPERUSER = "benji"
PREVIOUS_DEV_USER = "desarrollo"
# Columnas que dicen de quién es algo (no quién lo hizo en la bitácora).
_OWNER_COLUMNS = (
    ("searches", "user_id"),
    ("cases", "created_by"),
    ("case_members", "user_id"),
    ("case_members", "added_by"),
    ("case_articles", "added_by"),
    ("case_entities", "added_by"),
    ("concepts", "created_by"),
    ("reports", "created_by"),
)


def upgrade() -> None:
    """Crea personas y llaves, el superusuario y le pasa los datos de desarrollo."""
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('superuser', 'user')", name="users_role"),
        sa.CheckConstraint("btrim(username) <> ''", name="users_username_not_blank"),
    )
    op.create_index("users_username", "users", ["username"], unique=True)
    op.create_table(
        "access_keys",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", postgresql.INET(), nullable=True),
    )
    op.create_index("access_keys_prefix", "access_keys", ["key_prefix"], unique=True)
    op.create_index("access_keys_user", "access_keys", ["user_id"])
    op.execute(
        sa.text(
            "INSERT INTO users (username, display_name, role, created_by) "
            "VALUES (:u, 'Benjamin', 'superuser', 'migracion-0038')"
        ).bindparams(u=SUPERUSER)
    )
    for table, column in _OWNER_COLUMNS:
        op.execute(
            sa.text(
                f"UPDATE {table} SET {column} = :new WHERE {column} = :old"  # noqa: S608 — nombres fijos de esta migración
            ).bindparams(new=SUPERUSER, old=PREVIOUS_DEV_USER)
        )


def downgrade() -> None:
    """Regresa los datos al usuario de desarrollo y quita personas y llaves."""
    for table, column in _OWNER_COLUMNS:
        op.execute(
            sa.text(
                f"UPDATE {table} SET {column} = :old WHERE {column} = :new"  # noqa: S608 — nombres fijos de esta migración
            ).bindparams(new=SUPERUSER, old=PREVIOUS_DEV_USER)
        )
    op.drop_table("access_keys")
    op.drop_table("users")
