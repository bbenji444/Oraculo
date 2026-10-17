"""Guardar las pistas de la IA en cada mención de lugar (§11).

``article_locations`` guardaba el texto de la mención y su papel, pero no
las pistas que da la IA (``kind_hint``, ``state_hint``, ``country``). Sin
ellas no se puede volver a ubicar una nota con reglas nuevas del
geolocalizador sin pagarle otra vez a la IA (primera búsqueda real,
17/10/2026).

Las tres columnas son nulas: las filas anteriores no tienen pistas. No
llevan índice porque no se usan para filtrar, unir ni paginar.

Revisión: 0014
Anterior: 0013
Fecha: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega las columnas de pistas."""
    op.execute(
        """
        ALTER TABLE article_locations
            ADD COLUMN kind_hint text,
            ADD COLUMN state_hint text,
            ADD COLUMN country_hint text,
            ADD CONSTRAINT article_locations_kind_hint_known CHECK (
                kind_hint IN ('country', 'state', 'municipality', 'locality')
            )
        """
    )


def downgrade() -> None:
    """Quita las columnas (se pierden las pistas guardadas)."""
    op.execute(
        """
        ALTER TABLE article_locations
            DROP CONSTRAINT article_locations_kind_hint_known,
            DROP COLUMN kind_hint,
            DROP COLUMN state_hint,
            DROP COLUMN country_hint
        """
    )
