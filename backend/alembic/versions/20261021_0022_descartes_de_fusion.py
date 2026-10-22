"""Recordar los pares que el analista dijo que no son la misma entidad (Fase 9.5, D3).

Las sugerencias de fusión se calculan al leer (nombre igual, alias en común o
nombre parecido), así que siempre están al día. Lo único que hay que guardar
es la respuesta «No son la misma»: sin ella, el mismo par volvería a salir en
cada lectura.

- ``entity_merge_dismissals``: un renglón por caso y par de entidades, con el
  id menor primero (CHECK ``entity_low < entity_high``) para que A–B y B–A
  sean el mismo descarte, y quién lo decidió y cuándo.
- Borrar el caso o una de las entidades borra el descarte: sin ellas no
  significa nada.

Índices en la misma migración (CLAUDE.md §6.3): la llave primaria empieza por
el caso (así se consulta) y hay uno por cada entidad, para que borrar una no
recorra la tabla.

Revisión: 0022
Anterior: 0021
Fecha: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla y sus índices."""
    op.execute(
        """
        CREATE TABLE entity_merge_dismissals (
            case_id       uuid NOT NULL REFERENCES cases (id) ON DELETE CASCADE,
            entity_low    bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
            entity_high   bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
            dismissed_by  text NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (case_id, entity_low, entity_high),
            CONSTRAINT entity_merge_dismissals_ordered CHECK (entity_low < entity_high)
        )
        """
    )
    op.execute("CREATE INDEX entity_merge_dismissals_low ON entity_merge_dismissals (entity_low)")
    op.execute("CREATE INDEX entity_merge_dismissals_high ON entity_merge_dismissals (entity_high)")


def downgrade() -> None:
    """Elimina la tabla (las sugerencias descartadas vuelven a salir)."""
    op.execute("DROP TABLE entity_merge_dismissals")
