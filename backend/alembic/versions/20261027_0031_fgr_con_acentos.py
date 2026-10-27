"""Concepto FGR con acentos (F12, 27/10/2026).

El concepto semilla buscaba «Fiscalia General de la Republica», sin acentos.
Entre comillas Google lo toma casi literal. Medido el 27/10/2026 en Google News
RSS, con la ventana de la corrida FGR (25 y 26 de octubre):

- sin acentos: 4 notas;
- con acentos («Fiscalía General de la República»): 100 por día, el tope.

El índice local no cambia: compara sin acentos (``name_norm``).

Solo se toca el concepto si sigue tal como lo dejó la semilla. Si alguien ya
editó sus palabras clave en la pantalla de Conceptos, se respeta.
``name_norm`` no cambia, así que la corrida automática lo sigue encontrando.

Bajarla devuelve las palabras sin acentos.

Revisión: 0031
Anterior: 0030
Fecha: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME_NORM = "FISCALIA GENERAL DE LA REPUBLICA"
OLD_NAME = "Fiscalia General de la Republica"
NEW_NAME = "Fiscalía General de la República"
OLD_KEYWORDS = [OLD_NAME, "FGR"]
NEW_KEYWORDS = [NEW_NAME, "FGR"]

_SWAP = sa.text(
    "UPDATE concepts SET name = :new_name, keywords = CAST(:new_keywords AS text[]) "
    "WHERE name_norm = :norm AND deleted_at IS NULL "
    "AND keywords = CAST(:old_keywords AS text[])"
)


def upgrade() -> None:
    """Pone los acentos al nombre y a la palabra clave del concepto FGR."""
    op.execute(
        _SWAP.bindparams(
            new_name=NEW_NAME, new_keywords=NEW_KEYWORDS, norm=NAME_NORM, old_keywords=OLD_KEYWORDS
        )
    )


def downgrade() -> None:
    """Regresa el nombre y la palabra clave sin acentos."""
    op.execute(
        _SWAP.bindparams(
            new_name=OLD_NAME, new_keywords=OLD_KEYWORDS, norm=NAME_NORM, old_keywords=NEW_KEYWORDS
        )
    )
