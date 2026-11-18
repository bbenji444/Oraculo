"""Conceptos de búsqueda rápida (17/11/2026, ADR-0110).

Benji pidió buscar «como en el buscador de Google, para cuando no quieres
tener un concepto definido». Una búsqueda rápida crea por dentro un concepto
oculto con lo que escribió el analista y las frases de la IA, porque el
pipeline (juicio de la IA, ``search_concepts``, ``article_concepts``) se
apoya en conceptos.

Columna nueva:

- ``concepts.is_quick``: ``true`` en los de búsqueda rápida. No salen en la
  lista de conceptos ni ocupan su nombre; «Guardar como concepto» la pone en
  ``false``. Todos los que ya existen quedan en ``false``.

Índices: los tres índices parciales de la migración 0005 (nombre único y
paginación alfabética, con y sin «solo activos») se rehacen con
``AND NOT is_quick``, porque esas consultas ahora filtran también por ella.
A los ocultos solo se llega por su id (llave primaria).

Revisión: 0047
Anterior: 0046
Fecha: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Índices de la migración 0005: (nombre, columnas, si es único).
_INDEXES = (
    ("concepts_name_norm_active_key", "name_norm", True),
    ("concepts_name_id", "name_norm, id", False),
    ("concepts_active_name_id", "is_active, name_norm, id", False),
)


def _rebuild_indexes(where: str) -> None:
    for name, columns, unique in _INDEXES:
        op.execute(f"DROP INDEX {name}")
        kind = "UNIQUE INDEX" if unique else "INDEX"
        op.execute(f"CREATE {kind} {name} ON concepts ({columns}) WHERE {where}")


def upgrade() -> None:
    """Agrega ``is_quick`` en ``false`` y saca a los ocultos de los índices."""
    op.add_column(
        "concepts",
        sa.Column("is_quick", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _rebuild_indexes("deleted_at IS NULL AND NOT is_quick")


def downgrade() -> None:
    """Quita ``is_quick``; los de búsqueda rápida pasan a ser conceptos normales.

    Si alguno repite el nombre de otro vigente, el índice único no se puede
    rehacer: hay que renombrarlo o borrarlo antes de bajar.
    """
    _rebuild_indexes("deleted_at IS NULL")
    op.drop_column("concepts", "is_quick")
