"""Crear searches y search_concepts: cada búsqueda y sus conceptos (especificación §6).

Una fila de ``searches`` por búsqueda: quién, dónde, qué fechas, en qué etapa
va (``progress``) y cuánto costó (créditos de SearchApi y tokens de Gemini,
ADR-0015). ``search_concepts`` copia el nombre y las palabras de cada
concepto **al momento de buscar**, para que editar un concepto no cambie el
historial.

También conecta ``provider_queries.search_id`` con ``searches`` (la llave
foránea quedó pendiente desde F3); las consultas del comando de prueba
siguen sin búsqueda (``NULL``).

Índices en la misma migración (CLAUDE.md §6.3): (``created_at``, ``id``)
para paginar por cursor, (``user_id``, ``created_at``) para el historial de
cada persona, ``region_id`` y ``concept_id`` para sus llaves foráneas.

Revisión: 0011
Anterior: 0010
Fecha: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las tablas, sus índices y la llave foránea de provider_queries."""
    op.execute(
        """
        CREATE TABLE searches (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            -- Usuario de desarrollo hasta F8 (igual que audit_log.user_id).
            user_id            text NOT NULL,
            region_id          bigint NOT NULL REFERENCES regions (id),
            date_from          date NOT NULL,
            date_to            date NOT NULL,
            status             text NOT NULL DEFAULT 'pending',
            -- Etapa actual y conteos, para mostrar avance real (§9).
            progress           jsonb NOT NULL DEFAULT '{}',
            queries_planned    integer NOT NULL DEFAULT 0,
            credits_estimated  integer NOT NULL DEFAULT 0,
            credits_used       integer NOT NULL DEFAULT 0,
            -- Costo de Gemini (ADR-0015): tokens reales y costo estimado en USD.
            llm_tokens_in      bigint NOT NULL DEFAULT 0,
            llm_tokens_out     bigint NOT NULL DEFAULT 0,
            llm_cost_usd       numeric(10, 4) NOT NULL DEFAULT 0,
            results_count      integer NOT NULL DEFAULT 0,
            error_summary      text,
            started_at         timestamptz,
            finished_at        timestamptz,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT searches_status_known
                CHECK (status IN ('pending', 'running', 'completed', 'partial', 'failed')),
            CONSTRAINT searches_dates_in_order CHECK (date_from <= date_to),
            CONSTRAINT searches_counts_not_negative CHECK (
                queries_planned >= 0 AND credits_estimated >= 0 AND credits_used >= 0
                AND llm_tokens_in >= 0 AND llm_tokens_out >= 0 AND llm_cost_usd >= 0
                AND results_count >= 0
            )
        )
        """
    )
    op.execute("CREATE INDEX searches_created_id ON searches (created_at, id)")
    op.execute("CREATE INDEX searches_user_created ON searches (user_id, created_at)")
    op.execute("CREATE INDEX searches_region ON searches (region_id)")
    op.execute(
        """
        CREATE TABLE search_concepts (
            search_id      uuid NOT NULL REFERENCES searches (id) ON DELETE CASCADE,
            concept_id     bigint NOT NULL REFERENCES concepts (id),
            -- Copia al momento de buscar: editar el concepto no cambia el historial.
            concept_name   text NOT NULL,
            keywords       text[] NOT NULL,
            exclude_terms  text[] NOT NULL DEFAULT '{}',
            PRIMARY KEY (search_id, concept_id)
        )
        """
    )
    op.execute("CREATE INDEX search_concepts_concept ON search_concepts (concept_id)")
    op.execute(
        "ALTER TABLE provider_queries ADD CONSTRAINT provider_queries_search_fk "
        "FOREIGN KEY (search_id) REFERENCES searches (id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    """Quita la llave foránea y las tablas (se pierde el historial de búsquedas)."""
    op.execute("ALTER TABLE provider_queries DROP CONSTRAINT provider_queries_search_fk")
    op.execute("DROP TABLE search_concepts")
    op.execute("DROP TABLE searches")
