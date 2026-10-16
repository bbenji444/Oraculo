"""Crear la bitácora de auditoría (especificación §6 y §16, CLAUDE.md §8).

Cada cambio que importa queda registrado: quién, qué acción, sobre qué
entidad, con qué datos (antes y después) y desde qué IP. En F2 se registran
los cambios a conceptos; F4 y F7 agregan búsquedas y reportes.

Es de solo agregar: la aplicación nunca actualiza ni borra filas aquí.

Índices en la misma migración (CLAUDE.md §6.3): por fecha (paginación por
cursor ``created_at``, ``id``), por entidad ("historia de este concepto") y
por acción.

Revisión: 0006
Anterior: 0005
Fecha: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla y sus índices."""
    op.execute(
        """
        CREATE TABLE audit_log (
            id           bigserial PRIMARY KEY,
            -- Usuario fijo de desarrollo hasta F8 (DEV_USER), luego el real.
            user_id      text NOT NULL,
            -- Verbo estable en inglés: 'concept.created', 'concept.updated'...
            action       text NOT NULL,
            entity_type  text NOT NULL,
            entity_id    text NOT NULL,
            -- Datos del cambio: {"before": {...}, "after": {...}}.
            payload      jsonb NOT NULL DEFAULT '{}',
            -- Nulo cuando el cambio no vino de una petición HTTP (make seed).
            ip           inet,
            created_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX audit_log_created_id ON audit_log (created_at, id)")
    op.execute("CREATE INDEX audit_log_entity ON audit_log (entity_type, entity_id, created_at)")
    op.execute("CREATE INDEX audit_log_action ON audit_log (action, created_at)")


def downgrade() -> None:
    """Elimina la bitácora (se pierde el historial de auditoría)."""
    op.execute("DROP TABLE audit_log")
