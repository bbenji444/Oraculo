"""Un color por categoría (F12, 28/10/2026).

Las 15 categorías (0026 y 0029) se crearon sin color: «se definen después, con
datos». Benji pidió que cada tipo de noticia tenga su color en todo el
monitor: la barra del expediente, las etiquetas de la lista y la cronología, y
los puntos del globo.

La paleta sigue la consola táctica (ADR-0036): colores luminosos sobre negro,
uno distinto por categoría. Los delitos más violentos van en rojos y rosas,
los de dinero en azules y violetas, y «Otros» en gris, para no competir.

Solo se llena el color si está vacío: si alguien ya eligió uno, se respeta.
Bajarla deja vacíos los que esta migración puso.

Revisión: 0032
Anterior: 0031
Fecha: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# name_norm de cada categoría (mayúsculas, sin acentos) y su color.
COLORS: dict[str, str] = {
    "NARCOTRAFICO Y DELITOS CONTRA LA SALUD": "#2CF5A0",
    "DELINCUENCIA ORGANIZADA": "#9B8CFF",
    "SECUESTRO": "#F472B6",
    "DESAPARICION DE PERSONAS": "#C084FC",
    "HOMICIDIO": "#FF4D6D",
    "ARMAS Y EXPLOSIVOS": "#FACC15",
    "HUACHICOL Y DELITOS CONTRA HIDROCARBUROS": "#A3E635",
    "LAVADO DE DINERO Y DELITOS FISCALES": "#60A5FA",
    "CORRUPCION": "#E879F9",
    "TRATA DE PERSONAS": "#FDA4AF",
    "EXTORSION": "#818CF8",
    "CIBERDELITOS": "#00D2FF",
    "DELITOS ELECTORALES": "#5EEAD4",
    "OTROS": "#94A3B8",
    "SEGURIDAD NACIONAL (TRAICION A LA PATRIA)": "#38BDF8",
}

_SET = sa.text("UPDATE categories SET color = :color WHERE name_norm = :norm AND color IS NULL")
_CLEAR = sa.text("UPDATE categories SET color = NULL WHERE name_norm = :norm AND color = :color")


def upgrade() -> None:
    """Pone su color a cada categoría que todavía no tiene."""
    for norm, color in COLORS.items():
        op.execute(_SET.bindparams(norm=norm, color=color))


def downgrade() -> None:
    """Quita los colores que puso esta migración (los elegidos a mano se quedan)."""
    for norm, color in COLORS.items():
        op.execute(_CLEAR.bindparams(norm=norm, color=color))
