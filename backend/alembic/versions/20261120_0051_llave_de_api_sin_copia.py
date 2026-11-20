"""La llave de API se ve una sola vez: sin copia cifrada (20/11/2026, ADR-0120).

Benji: «necesito que me permitas ver una sola vez la api key y después no se
pueda ver de nuevo bajo ningún motivo, solo generar una nueva».

Hasta ahora (ADR-0047, migración 0044) la llave completa se guardaba cifrada
en ``access_keys.secret_sealed`` para que un superusuario la volviera a ver
con «Copiar». Esa copia era lo único que permitía verla otra vez, así que se
borra la columna: el servidor ya no puede mostrar una llave después de
crearla. Comprobar una llave no cambia, porque sigue siendo con su huella
HMAC (``key_hash``). **Las llaves que ya existen siguen sirviendo** y lo
único que se pierde es poder volver a verlas.

Cambios:

- ``access_keys.is_api_key``: marca cuál es la llave de API de la persona
  (la que se reemplaza con «Generar nueva»), para distinguirla de las llaves
  de sistema. Antes lo decía ``secret_sealed IS NOT NULL`` y así se llena.
- Índice parcial ``(user_id) WHERE is_api_key AND revoked_at IS NULL``: la
  lista de «Accesos» y «Generar nueva» buscan la llave de API vigente de cada
  persona.
- Se borra ``access_keys.secret_sealed``.

Bajar vuelve a crear ``secret_sealed`` **vacía** (las copias no se pueden
recuperar) y quita la marca. Las llaves de API quedan como llaves de sistema
que siguen sirviendo. No se hace sin respaldo (``make db-dump``).

Revisión: 0051
Anterior: 0050
Fecha: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "access_keys_api_key_active"


def upgrade() -> None:
    """Marca las llaves de API y borra sus copias cifradas."""
    op.add_column(
        "access_keys",
        sa.Column("is_api_key", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE access_keys SET is_api_key = true WHERE secret_sealed IS NOT NULL")
    op.create_index(
        _INDEX,
        "access_keys",
        ["user_id"],
        postgresql_where=sa.text("is_api_key AND revoked_at IS NULL"),
    )
    op.drop_column("access_keys", "secret_sealed")


def downgrade() -> None:
    """Vuelve a crear la columna de la copia, vacía, y quita la marca."""
    op.add_column("access_keys", sa.Column("secret_sealed", sa.Text(), nullable=True))
    op.drop_index(_INDEX, table_name="access_keys")
    op.drop_column("access_keys", "is_api_key")
