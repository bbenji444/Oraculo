"""Crear ingest_runs: registro de cada corrida de la ingesta (ADR-0013).

Una fila por archivo de GDELT o por lectura de un feed RSS: qué se bajó,
cuántos bytes, cuántas notas se vieron, cuántas se guardaron y si falló.
Sirve para auditar el consumo de internet y para no procesar dos veces el
mismo archivo: ``dedupe_key`` (la URL del archivo de GDELT) es única entre
las corridas exitosas. Los feeds RSS no la usan: se leen en cada corrida.

Índices en la misma migración (CLAUDE.md §6.3): (``source``, ``started_at``)
para ver la historia de una fuente, y el único parcial de ``dedupe_key``.

Revisión: 0009
Anterior: 0008
Fecha: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea la tabla y sus índices."""
    op.execute(
        """
        CREATE TABLE ingest_runs (
            id                bigserial PRIMARY KEY,
            source            text NOT NULL,
            -- Archivo o feed leído.
            item              text NOT NULL,
            -- Archivo de GDELT ya procesado; vacío en los feeds RSS.
            dedupe_key        text,
            status            text NOT NULL,
            bytes_downloaded  bigint NOT NULL DEFAULT 0,
            items_seen        integer NOT NULL DEFAULT 0,
            items_kept        integer NOT NULL DEFAULT 0,
            items_new         integer NOT NULL DEFAULT 0,
            error_message     text,
            started_at        timestamptz NOT NULL DEFAULT now(),
            finished_at       timestamptz,
            CONSTRAINT ingest_runs_status_known CHECK (status IN ('ok', 'error', 'skipped')),
            CONSTRAINT ingest_runs_counts_not_negative CHECK (
                bytes_downloaded >= 0 AND items_seen >= 0 AND items_kept >= 0 AND items_new >= 0
            )
        )
        """
    )
    op.execute("CREATE INDEX ingest_runs_source_started ON ingest_runs (source, started_at)")
    op.execute(
        "CREATE UNIQUE INDEX ingest_runs_dedupe_ok_key ON ingest_runs (dedupe_key) "
        "WHERE status = 'ok' AND dedupe_key IS NOT NULL"
    )


def downgrade() -> None:
    """Elimina el registro de corridas."""
    op.execute("DROP TABLE ingest_runs")
