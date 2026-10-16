"""Crear la tabla concepts: plantillas de búsqueda del analista (§6, §7).

Las reglas de negocio viven en ``app.domain.concept``; aquí la base
garantiza las mínimas, por si alguien escribe directo con SQL:

- Nombre único **entre los conceptos no borrados**, comparando
  ``name_norm`` (mayúsculas, sin acentos, con Ñ): borrar un concepto
  libera su nombre.
- Al menos una palabra clave y color ``#RRGGBB``.

``deleted_at`` es el borrado lógico: un concepto usado en búsquedas no se
borra de verdad, para que el historial siga mostrando su nombre (§13).

Índices en la misma migración (CLAUDE.md §6.3): el único parcial de nombre y
los de paginación alfabética por cursor (``name_norm``, ``id``), con y sin
el filtro de activos.

Revisión: 0005
Anterior: 0004
Fecha: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla, sus índices y su disparador de updated_at."""
    op.execute(
        """
        CREATE TABLE concepts (
            id              bigserial PRIMARY KEY,
            -- Nombre como lo escribió la persona; name_norm para comparar.
            name            text NOT NULL,
            name_norm       text NOT NULL,
            description     text NOT NULL DEFAULT '',
            keywords        text[] NOT NULL,
            exclude_terms   text[] NOT NULL DEFAULT '{}',
            color           text NOT NULL,
            is_active       boolean NOT NULL DEFAULT true,
            created_by      text NOT NULL,
            -- Borrado lógico: NULL = vigente.
            deleted_at      timestamptz,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT concepts_has_keywords CHECK (cardinality(keywords) >= 1),
            CONSTRAINT concepts_color_hex CHECK (color ~ '^#[0-9A-F]{6}$'),
            CONSTRAINT concepts_name_not_blank CHECK (btrim(name) <> '')
        )
        """
    )
    # Unicidad del nombre solo entre los vigentes: un nombre borrado se reusa.
    op.execute(
        "CREATE UNIQUE INDEX concepts_name_norm_active_key ON concepts (name_norm) "
        "WHERE deleted_at IS NULL"
    )
    # Paginación alfabética por cursor (name_norm, id), nunca OFFSET.
    op.execute("CREATE INDEX concepts_name_id ON concepts (name_norm, id) WHERE deleted_at IS NULL")
    # "Solo activos" (panel de búsqueda), con el mismo orden.
    op.execute(
        "CREATE INDEX concepts_active_name_id ON concepts (is_active, name_norm, id) "
        "WHERE deleted_at IS NULL"
    )
    # set_updated_at() la creó la migración 0002.
    op.execute(
        "CREATE TRIGGER concepts_set_updated_at BEFORE UPDATE ON concepts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    """Elimina la tabla (borra los conceptos)."""
    op.execute("DROP TABLE concepts")
