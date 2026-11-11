"""Código de 6 dígitos opcional y llave de API visible por usuario (11/11/2026, ADR-0047).

Benji: «vamos a quitar lo de la autenticación con código, dice mi jefe que
es tedioso», pero con un interruptor en el panel para volver a pedirlo; y
«cada usuario debe tener su propia API key… que puedas copiar».

Cambios:

- ``auth_settings``: una sola fila con ``totp_required``. Arranca en
  ``false``: se entra con usuario y contraseña. El superusuario lo prende o
  apaga desde «Accesos». Los secretos de Authenticator ya dados de alta se
  quedan guardados: si se vuelve a prender, siguen sirviendo.
- ``access_keys.secret_sealed``: la llave completa **cifrada** (AES-GCM con
  la pimienta del servidor), para que el superusuario la pueda volver a ver
  y copiar. La comprobación sigue siendo con la huella HMAC (``key_hash``);
  las llaves viejas no la tienen y no se pueden mostrar (se genera una nueva).

Sin seguridad por filas en ``auth_settings``: no tiene nada secreto y solo
se cambia por una ruta de superusuario.

Revisión: 0044
Anterior: 0043
Fecha: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea el interruptor del código y el lugar de la llave cifrada."""
    op.create_table(
        "auth_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True, server_default="1"),
        sa.Column("totp_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.CheckConstraint("id = 1", name="auth_settings_single_row"),
    )
    op.execute("INSERT INTO auth_settings (id, totp_required) VALUES (1, false)")
    op.add_column("access_keys", sa.Column("secret_sealed", sa.Text(), nullable=True))


def downgrade() -> None:
    """Quita el interruptor (vuelve a pedirse siempre el código) y las llaves cifradas."""
    op.drop_column("access_keys", "secret_sealed")
    op.drop_table("auth_settings")
