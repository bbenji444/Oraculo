"""Quitar las comillas de los nombres de comparación de entidades (Fase 9.5, D1).

La 9.4 guardó ``entities.label_norm`` y ``entity_aliases.alias_norm`` con las
comillas del medio: "JULIAN “N”", "JULIAN 'N'" y "JULIAN N" quedaron como
tres sugerencias distintas de la misma persona. Desde la 9.5 el código compara
con ``app.domain.entity_resolution.entity_name_norm``, que cambia las comillas
por espacios; esta migración aplica la misma regla a lo ya guardado.

- Solo cambia los nombres de comparación. El nombre que se muestra
  (``canonical_label`` y ``alias``) queda intacto (CLAUDE.md §6.3).
- Si dos alias de la misma entidad quedan iguales, se conserva el más antiguo
  y se borran los demás (aprobado en el plan de la 9.5): la llave única
  (``entity_id``, ``alias_norm``) no admite dos.
- Las entidades duplicadas que ya existen **no se juntan**: aparecen como
  sugerencia de fusión «mismo nombre» y las une una persona (ADR-0104).
- Las lecturas guardadas de la IA (``entity_extractions.output``) no se tocan:
  el repositorio recalcula el nombre al reutilizarlas.

``downgrade`` no hace nada: las comillas no se pueden recuperar, y dejar los
nombres sin ellas no rompe a la 0020.

Revisión: 0021
Anterior: 0020
Fecha: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Las mismas comillas que entity_resolution._QUOTES_TO_SPACE, aquí escritas: una
# migración no debe cambiar si el código cambia después. La prueba de esta
# migración compara su resultado con entity_name_norm.
_QUOTES = "[\"'“”«»‘’„]"


def _without_quotes(column: str) -> str:
    """Expresión SQL: comillas por espacios, sin espacios repetidos ni en los extremos."""
    quotes = _QUOTES.replace("'", "''")
    return (
        f"btrim(regexp_replace(regexp_replace({column}, '{quotes}', ' ', 'g'), '\\s+', ' ', 'g'))"
    )


def upgrade() -> None:
    """Recalcula los nombres de comparación y junta los alias que quedan repetidos."""
    alias_norm = _without_quotes("alias_norm")
    op.execute(
        f"""
        DELETE FROM entity_aliases WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY entity_id, {alias_norm} ORDER BY id
                ) AS copy
                FROM entity_aliases
            ) ranked
            WHERE copy > 1
        )
        """  # noqa: S608 — expresión fija de este módulo, sin datos de afuera
    )
    op.execute(
        f"UPDATE entity_aliases SET alias_norm = {alias_norm} "  # noqa: S608 — expresión fija
        f"WHERE alias_norm <> {alias_norm}"
    )
    label_norm = _without_quotes("label_norm")
    op.execute(
        f"UPDATE entities SET label_norm = {label_norm}, updated_at = now() "  # noqa: S608 — fija
        f"WHERE label_norm <> {label_norm}"
    )


def downgrade() -> None:
    """No hace nada: las comillas no se recuperan y la 0020 funciona sin ellas."""
