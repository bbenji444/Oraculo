"""Crear processing_errors: lo que falló al procesar una nota o una búsqueda (§9).

Un error en una nota (extracción, IA, geolocalización) se anota aquí y la
búsqueda sigue con las demás. Si en una etapa falla más de la mitad, la
búsqueda queda ``partial`` con su resumen.

Índices en la misma migración (CLAUDE.md §6.3): ``search_id`` y
``article_id`` (llaves foráneas) y (``created_at``, ``id``) para paginar.

Revisión: 0013
Anterior: 0012
Fecha: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla y sus índices."""
    op.execute(
        """
        CREATE TABLE processing_errors (
            id          bigserial PRIMARY KEY,
            search_id   uuid REFERENCES searches (id) ON DELETE CASCADE,
            article_id  bigint REFERENCES articles (id) ON DELETE CASCADE,
            -- Etapa del pipeline (§9): plan, query, dedupe, extract, enrich, geocode...
            stage       text NOT NULL,
            error_type  text NOT NULL,
            message     text NOT NULL,
            payload     jsonb NOT NULL DEFAULT '{}',
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX processing_errors_search ON processing_errors (search_id)")
    op.execute("CREATE INDEX processing_errors_article ON processing_errors (article_id)")
    op.execute("CREATE INDEX processing_errors_created_id ON processing_errors (created_at, id)")


def downgrade() -> None:
    """Elimina la tabla (se pierde el registro de errores)."""
    op.execute("DROP TABLE processing_errors")
