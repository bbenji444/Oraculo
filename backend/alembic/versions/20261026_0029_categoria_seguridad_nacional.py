"""Categoría «Seguridad nacional (traición a la patria)» (F12.4, ADR-0029).

En las corridas FGR del 26/10/2026, el 72 % de las notas quedaba en «Otros»
(169 de 235 a las 15:00). La IA proponía sola la etiqueta libre «traición a la
patria» en 90 notas: el caso Jáuregui y la presencia de agentes extranjeros en
Chihuahua. Benji aprobó agregarla el mismo día.

Va justo antes de «Otros» en el orden del catálogo (``sort_order``), así que
«Otros» baja un lugar. No agrega columnas ni índices: el catálogo ya los tiene
(``categories_name_norm`` y ``articles_category``).

Bajarla borra la categoría. Las notas que la tenían quedan sin categoría
(``ON DELETE SET NULL``) y se vuelven a clasificar con ``make clasificar``.

Revisión: 0029
Anterior: 0028
Fecha: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "Seguridad nacional (traición a la patria)"
# Igual que ``normalize_name(NAME)``: mayúsculas, sin acentos, conservando la Ñ.
NAME_NORM = "SEGURIDAD NACIONAL (TRAICION A LA PATRIA)"
DESCRIPTION = (
    "Traición a la patria, espionaje, sabotaje o actos contra la soberanía y la "
    "seguridad de la nación, como permitir que agentes extranjeros operen sin "
    "autorización. Incluye lo que rodea a esos casos: audiencias, protestas, "
    "cartas o declaraciones de los acusados."
)


def upgrade() -> None:
    """Agrega la categoría justo antes de «Otros»."""
    op.execute("UPDATE categories SET sort_order = sort_order + 1 WHERE is_other")
    op.execute(
        sa.text(
            "INSERT INTO categories (name, name_norm, description, sort_order, is_other) "
            "SELECT :name, :norm, :description, sort_order - 1, false "
            "FROM categories WHERE is_other"
        ).bindparams(name=NAME, norm=NAME_NORM, description=DESCRIPTION)
    )


def downgrade() -> None:
    """Quita la categoría y devuelve «Otros» a su lugar."""
    op.execute(sa.text("DELETE FROM categories WHERE name_norm = :norm").bindparams(norm=NAME_NORM))
    op.execute("UPDATE categories SET sort_order = sort_order - 1 WHERE is_other")
