"""Términos obligatorios: los nombres propios de la búsqueda rápida (18/11/2026, ADR-0113).

Benji buscó «Hacker Eternal» en la búsqueda rápida: la IA lo volvió
«Hackeo Eternal», sus frases perdieron el nombre y el juicio no sabía que
una nota tenía que tratar de Eternal. Ahora la IA marca los nombres propios
que escribió el analista (prompt ``terms_v3``), el código deja solo los que
están tal cual en el texto y se guardan con el concepto oculto.

Columnas nuevas:

- ``concepts.required_terms``: nombres propios, alias, grupos o siglas que
  escribió el analista («Eternal»). Todos los conceptos que ya existen
  quedan con la lista vacía: la FGR, los temas de las subdivisiones y los de
  cada analista se buscan y juzgan igual que antes.
- ``search_concepts.required_terms``: la copia al buscar, junto con las
  palabras clave y el modo, para que el pipeline los tenga a mano aunque el
  concepto cambie después.

Sin índices: ninguna consulta filtra, une ni pagina por estas columnas; se
leen junto con el concepto o con la búsqueda, que ya se buscan por su id.

Revisión: 0049
Anterior: 0048
Fecha: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("concepts", "search_concepts")


def upgrade() -> None:
    """Agrega ``required_terms`` vacío para todo lo que ya existe."""
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "required_terms",
                postgresql.ARRAY(sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::text[]"),
            ),
        )


def downgrade() -> None:
    """Quita ``required_terms``; las búsquedas rápidas pierden sus nombres propios."""
    for table in _TABLES:
        op.drop_column(table, "required_terms")
