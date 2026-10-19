"""Tabla ``reports``: el resumen ejecutivo de cada búsqueda (F7, ADR-0018).

El reporte en PDF lleva un resumen ejecutivo que escribe la IA a partir de
los resúmenes de las notas. Se guarda aquí para que pedir el reporte otra
vez (o en otro formato) no vuelva a pagarle a la IA.

Una fila por búsqueda: ``search_id`` es único, y esa restricción crea el
índice con el que se busca. Si la búsqueda se borra, su resumen también.

Revisión: 0015
Anterior: 0014
Fecha: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla."""
    op.execute(
        """
        CREATE TABLE reports (
            id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            search_id          uuid NOT NULL UNIQUE REFERENCES searches (id) ON DELETE CASCADE,
            executive_summary  text NOT NULL,
            llm_provider       text NOT NULL,
            llm_model          text NOT NULL,
            prompt_version     text NOT NULL,
            llm_tokens_in      integer NOT NULL DEFAULT 0,
            llm_tokens_out     integer NOT NULL DEFAULT 0,
            llm_cost_usd       numeric(10, 4) NOT NULL DEFAULT 0,
            -- Usuario de desarrollo hasta F8 (igual que searches.user_id).
            created_by         text NOT NULL,
            created_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT reports_usage_non_negative CHECK (
                llm_tokens_in >= 0 AND llm_tokens_out >= 0 AND llm_cost_usd >= 0
            )
        )
        """
    )


def downgrade() -> None:
    """Borra la tabla (se pierden los resúmenes ya pagados)."""
    op.execute("DROP TABLE reports")
