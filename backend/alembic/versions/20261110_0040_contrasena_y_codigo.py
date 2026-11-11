"""Contraseña y código de 6 dígitos de cada persona (10/11/2026, ADR-0043).

Benji pidió entrar al monitor igual que a Oráculo: usuario, contraseña y el
código de Microsoft Authenticator. Columnas nuevas en ``users``:

- ``password_hash``: huella scrypt (nunca la contraseña); ``NULL`` = todavía
  no tiene contraseña;
- ``must_change_password``: la contraseña es temporal y se cambia al entrar;
- ``totp_secret``: secreto del código de 6 dígitos **cifrado** con AES-GCM
  (la llave sale de ``AUTH_KEY_PEPPER``, fuera de la base); ``NULL`` = falta
  dar de alta su Authenticator;
- ``totp_enrolled_at``: cuándo lo dio de alta;
- ``totp_last_counter``: último periodo de código usado, para que un código
  no sirva dos veces;
- ``failed_logins`` y ``locked_until``: 5 fallos seguidos bloquean 15 min;
- ``password_changed_at``: última vez que cambió su contraseña.

Sin índices nuevos: todo se busca por ``username`` o ``id``, que ya los tienen.
La tabla sigue con su seguridad por filas (migración 0039).

Revisión: 0040
Anterior: 0039
Fecha: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    sa.Column("password_hash", sa.Text(), nullable=True),
    sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("totp_secret", sa.Text(), nullable=True),
    sa.Column("totp_enrolled_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("totp_last_counter", sa.BigInteger(), nullable=True),
    sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    """Agrega las columnas de contraseña, código y bloqueo."""
    for column in _COLUMNS:
        op.add_column("users", column)


def downgrade() -> None:
    """Quita las columnas (se pierden contraseñas y Authenticators)."""
    for column in reversed(_COLUMNS):
        op.drop_column("users", column.name)
