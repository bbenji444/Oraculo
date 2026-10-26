"""Quién actúa en cada nota y la regla de relevancia de cada concepto (F12.5, ADR-0030).

- ``articles.authority``: quién actúa en el hecho principal según la IA
  (``fgr``, ``fgr_mencion``, ``estatal``, ``otra`` o ``sin_dato``), o ``NULL``
  si la nota no se ha clasificado. Lo llena la clasificación (classify_v2).
- ``concepts.relevance_rule``: ``general`` (la relevancia es la de la IA) o
  ``fgr_federal`` (además tiene que actuar la FGR federal). Se pone
  ``fgr_federal`` en el concepto «Fiscalia General de la Republica».

Índice en la misma migración (CLAUDE.md §6.3): por ``authority``, porque la
relevancia de las búsquedas FGR, el reporte y la línea de tiempo filtran por él.

Revisión: 0027
Anterior: 0026
Fecha: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores de app.domain.authority; se copian aquí porque una migración no
# debe cambiar si el código cambia después.
_AUTHORITIES = "'fgr', 'fgr_mencion', 'estatal', 'otra', 'sin_dato'"
_RULES = "'general', 'fgr_federal'"
# name_norm del concepto que creó Benji el 24/10/2026 (mayúsculas, sin acentos).
_FGR_CONCEPT = "FISCALIA GENERAL DE LA REPUBLICA"


def upgrade() -> None:
    """Agrega quién actúa, la regla de relevancia y la pone en el concepto FGR."""
    op.execute(
        f"ALTER TABLE articles ADD COLUMN authority text CHECK (authority IN ({_AUTHORITIES}))"
    )
    op.execute(
        "CREATE INDEX articles_authority ON articles (authority) WHERE authority IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE concepts ADD COLUMN relevance_rule text NOT NULL DEFAULT 'general' "
        f"CHECK (relevance_rule IN ({_RULES}))"
    )
    op.execute(
        sa.text(
            "UPDATE concepts SET relevance_rule = 'fgr_federal' "
            "WHERE name_norm = :norm AND deleted_at IS NULL"
        ).bindparams(norm=_FGR_CONCEPT)
    )


def downgrade() -> None:
    """Quita la regla de los conceptos y quién actúa de las notas."""
    op.execute("ALTER TABLE concepts DROP COLUMN relevance_rule")
    op.execute("DROP INDEX articles_authority")
    op.execute("ALTER TABLE articles DROP COLUMN authority")
