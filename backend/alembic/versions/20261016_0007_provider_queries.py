"""Crear provider_queries: cada petición a un proveedor de noticias (§6, §8).

Registra todas las peticiones, también las del comando de prueba y las
respondidas desde la caché, con su resultado y los créditos que costaron.
Sirve para auditar el gasto y para el tope mensual de créditos de
SearchApi (se suma ``cost_credits`` del mes).

``search_id`` es opcional: la tabla ``searches`` llega en F4/F5, y entonces
se agrega la llave foránea. Las consultas del comando de prueba no
pertenecen a ninguna búsqueda.

Índices en la misma migración (CLAUDE.md §6.3): (``provider``,
``created_at``) para el contador mensual, ``search_id`` para ver las
consultas de una búsqueda y (``created_at``, ``id``) para paginar.

Revisión: 0007
Anterior: 0006
Fecha: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla y sus índices."""
    op.execute(
        """
        CREATE TABLE provider_queries (
            id             bigserial PRIMARY KEY,
            search_id      uuid,
            provider       text NOT NULL,
            -- Texto exacto enviado y parámetros (sin la llave).
            query_text     text NOT NULL,
            params         jsonb NOT NULL DEFAULT '{}',
            -- ok: respondió; error: falló tras los reintentos; skipped: no se
            -- envió (sin llave o sin presupuesto).
            status         text NOT NULL,
            http_status    integer,
            results_count  integer NOT NULL DEFAULT 0,
            from_cache     boolean NOT NULL DEFAULT false,
            cost_credits   integer NOT NULL DEFAULT 0,
            duration_ms    integer NOT NULL DEFAULT 0,
            error_message  text,
            created_at     timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT provider_queries_status_known
                CHECK (status IN ('ok', 'error', 'skipped')),
            CONSTRAINT provider_queries_counts_not_negative
                CHECK (results_count >= 0 AND cost_credits >= 0 AND duration_ms >= 0),
            -- Una respuesta de la caché nunca cuesta créditos.
            CONSTRAINT provider_queries_cache_is_free
                CHECK (NOT from_cache OR cost_credits = 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX provider_queries_provider_created ON provider_queries (provider, created_at)"
    )
    op.execute("CREATE INDEX provider_queries_search ON provider_queries (search_id)")
    op.execute("CREATE INDEX provider_queries_created_id ON provider_queries (created_at, id)")


def downgrade() -> None:
    """Elimina la tabla (se pierde el registro de peticiones y créditos)."""
    op.execute("DROP TABLE provider_queries")
