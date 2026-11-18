"""Modo de búsqueda de cada concepto: frases exactas o «como en Google» (17/11/2026, ADR-0109).

Benji notó que un concepto trae menos notas que buscar la misma noticia en
Google. Medido el 17/11/2026 en Google News RSS: «"bases de datos
hackeadas"» con comillas trajo 0 notas y sin comillas 10. En modo ``open``
cada frase se manda sola y sin comillas.

Columnas nuevas:

- ``concepts.query_mode``: ``exact`` (como hasta hoy) u ``open``. Todos los
  conceptos que ya existen quedan en ``exact``: la FGR, los temas de las
  subdivisiones y los de cada analista se buscan igual que antes.
- ``search_concepts.query_mode``: el modo copiado al buscar, junto con las
  palabras clave, para poder rehacer la consulta tal como se mandó.

Sin índices: ninguna consulta filtra, une ni pagina por el modo.

Revisión: 0046
Anterior: 0045
Fecha: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("concepts", "search_concepts")
_MODES = "('exact', 'open')"


def upgrade() -> None:
    """Agrega ``query_mode`` con ``exact`` para todo lo que ya existe."""
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("query_mode", sa.Text(), nullable=False, server_default="exact"),
        )
        op.create_check_constraint(f"{table}_query_mode_check", table, f"query_mode IN {_MODES}")


def downgrade() -> None:
    """Quita ``query_mode``; los conceptos abiertos vuelven a buscarse exactos."""
    for table in _TABLES:
        op.drop_constraint(f"{table}_query_mode_check", table, type_="check")
        op.drop_column(table, "query_mode")
