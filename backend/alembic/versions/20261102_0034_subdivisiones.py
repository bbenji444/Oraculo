"""Subdivisiones: un tema general por categoría y búsquedas con subdivisión (02/11/2026).

Benji pidió dos cosas:

- buscar un tema en general, sin la FGR («si un día quisiera ver únicamente
  homicidios»): cada categoría del catálogo puede tener un concepto propio,
  con sus palabras clave. ``concepts.category_id`` los enlaza; hay a lo más un
  concepto vigente por categoría;
- buscar la FGR con una subdivisión («FGR + Homicidio») y que cada nota
  traiga las dos cosas. La búsqueda copia en ``search_concepts`` las palabras
  de la subdivisión (``topic_terms``), que deben aparecer junto con las del
  concepto, y qué subdivisiones se eligieron (``category_ids``).

Índices: ``concepts.category_id`` se usa para unir y buscar el tema de una
categoría (índice único parcial, que también cuida que haya uno solo). Las dos
columnas nuevas de ``search_concepts`` solo se leen junto con su búsqueda,
que ya tiene índice: no llevan uno propio.

Revisión: 0034
Anterior: 0033
Fecha: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enlaza conceptos con categorías y guarda las subdivisiones de cada búsqueda."""
    op.add_column(
        "concepts",
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "concepts_one_per_category",
        "concepts",
        ["category_id"],
        unique=True,
        postgresql_where=sa.text("category_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.add_column(
        "search_concepts",
        sa.Column(
            "topic_terms",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "search_concepts",
        sa.Column(
            "category_ids",
            postgresql.ARRAY(sa.BigInteger()),
            nullable=False,
            server_default=sa.text("'{}'::bigint[]"),
        ),
    )


def downgrade() -> None:
    """Quita el enlace y las subdivisiones."""
    op.drop_column("search_concepts", "category_ids")
    op.drop_column("search_concepts", "topic_terms")
    op.drop_index("concepts_one_per_category", table_name="concepts")
    op.drop_column("concepts", "category_id")
