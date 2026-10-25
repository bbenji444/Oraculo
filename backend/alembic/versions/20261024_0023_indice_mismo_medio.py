"""Índice para no guardar dos veces la misma nota de un medio (F12.1b, ADR-0025).

Antes de insertar en ``news_index``, la ingesta revisa si el **mismo medio**
ya tiene el mismo texto (``text_norm``) a ±3 días. Esa consulta filtra por
``source_domain`` y por rango de ``published_at``, así que lleva su índice en
la misma migración (CLAUDE.md §6.3). Sin él, cada nota nueva recorrería las
~77,000 del índice.

Revisión: 0023
Anterior: 0022
Fecha: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea el índice por medio y fecha."""
    op.execute(
        "CREATE INDEX news_index_domain_published ON news_index (source_domain, published_at)"
    )


def downgrade() -> None:
    """Quita el índice."""
    op.execute("DROP INDEX news_index_domain_published")
