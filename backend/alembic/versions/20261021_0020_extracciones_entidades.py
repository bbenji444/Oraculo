"""Registrar las extracciones de entidades y su estado por nota del caso (Fase 9.4).

La IA lee cada noticia que entra a un caso y propone personas,
organizaciones, lugares y vehículos (ADR-0103). Esta migración guarda lo
necesario para hacerlo **una sola vez por nota** y para saber qué falta:

- ``entity_extractions``: lo que respondió la IA de una nota, ya revisado
  contra el texto (solo quedan las entidades cuya cita aparece en la nota) y
  lo que se descartó por no estar. Llave (``article_id``, ``prompt_version``):
  si la misma nota entra a otro caso se reutiliza sin volver a pagar; un
  prompt nuevo sí la vuelve a leer. Guarda modelo, tokens, costo y error, y
  de dónde salió el texto (``full_text`` o ``title_snippet`` cuando el texto
  ya se borró a los 30 días, ADR-0015).
- ``case_articles.entities_status``: en qué va cada nota del caso
  (``pending`` sin pedir, ``queued`` en la cola, ``done``, ``failed`` o
  ``skipped`` por el tope del caso) y ``entities_cost_usd``, lo que ESTE caso
  pagó por ella (0 si se reutilizó). Las notas que ya estaban quedan
  ``pending``: el caso ofrece analizarlas.
- ``entity_mentions``: una mención no se repite (misma entidad, nota y cita):
  volver a agregar una nota que se había quitado no duplica la evidencia.

Índices en la misma migración (CLAUDE.md §6.3): la llave única de
``entity_extractions`` sirve para buscar por nota; el parcial de
``case_articles`` encuentra lo que falta analizar de un caso.

Revisión: 0020
Anterior: 0019
Fecha: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores de app.domain.entity_extraction (aquí escritos: una migración no
# debe cambiar si el código cambia después).
_CASE_ARTICLE_STATUSES = "'pending', 'queued', 'done', 'failed', 'skipped'"


def upgrade() -> None:
    """Crea la tabla, las columnas y los índices."""
    op.execute(
        """
        CREATE TABLE entity_extractions (
            id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            article_id      bigint NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
            prompt_version  text NOT NULL,
            status          text NOT NULL,
            model           text NOT NULL,
            -- De dónde salió el texto que leyó la IA (ADR-0015: el cuerpo se borra).
            source          text NOT NULL,
            -- Entidades que pasaron la revisión contra el texto y las descartadas,
            -- con su motivo. Nulo si la IA no dio una respuesta válida.
            output          jsonb,
            rejected_count  integer NOT NULL DEFAULT 0,
            -- Suma de todos los intentos (los fallidos también se cobran).
            tokens_in       integer NOT NULL DEFAULT 0,
            tokens_out      integer NOT NULL DEFAULT 0,
            cost_usd        numeric(12, 6) NOT NULL DEFAULT 0,
            error           text,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (article_id, prompt_version),
            CONSTRAINT entity_extractions_status_known CHECK (status IN ('ok', 'failed')),
            CONSTRAINT entity_extractions_source_known
                CHECK (source IN ('full_text', 'title_snippet')),
            CONSTRAINT entity_extractions_output_when_ok
                CHECK ((status = 'ok') = (output IS NOT NULL)),
            CONSTRAINT entity_extractions_counts_positive CHECK (
                rejected_count >= 0 AND tokens_in >= 0 AND tokens_out >= 0 AND cost_usd >= 0
            )
        )
        """
    )

    op.execute(
        f"""
        ALTER TABLE case_articles
            ADD COLUMN entities_status text NOT NULL DEFAULT 'pending',
            ADD COLUMN entities_cost_usd numeric(12, 6) NOT NULL DEFAULT 0,
            ADD CONSTRAINT case_articles_entities_status_known
                CHECK (entities_status IN ({_CASE_ARTICLE_STATUSES})),
            ADD CONSTRAINT case_articles_entities_cost_positive CHECK (entities_cost_usd >= 0)
        """
    )
    # "Analizar pendientes" busca solo lo que falta de un caso.
    op.execute(
        "CREATE INDEX case_articles_entities_todo ON case_articles (case_id) "
        "WHERE entities_status IN ('pending', 'failed')"
    )

    op.execute(
        "CREATE UNIQUE INDEX entity_mentions_once "
        "ON entity_mentions (entity_id, article_id, evidence_span)"
    )


def downgrade() -> None:
    """Quita la tabla y las columnas (se pierde lo extraído; las entidades quedan)."""
    op.execute("DROP INDEX entity_mentions_once")
    op.execute("DROP INDEX case_articles_entities_todo")
    op.execute(
        """
        ALTER TABLE case_articles
            DROP CONSTRAINT case_articles_entities_cost_positive,
            DROP CONSTRAINT case_articles_entities_status_known,
            DROP COLUMN entities_cost_usd,
            DROP COLUMN entities_status
        """
    )
    op.execute("DROP TABLE entity_extractions")
