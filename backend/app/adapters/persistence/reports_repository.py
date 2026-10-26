"""``ReportStorePort`` sobre PostgreSQL (especificación §15 y §16, ADR-0018).

- ``reports``: el resumen ejecutivo de cada búsqueda, para no volver a
  pagarlo. Si dos reportes lo escriben a la vez, se queda el primero.
- ``provider_queries``: consultas, notas y créditos por proveedor (pie del
  reporte).
- ``audit_log``: un ``report.generated`` por cada reporte o exportación.

No hace: no decide qué va en el reporte (eso es ``BuildReport``).
"""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.audit import REPORT_GENERATED, Actor
from app.application.ports.reports import ProviderUsage, StoredSummary
from app.domain.enrichment import LLMUsage

# Los reportes son de una búsqueda: así se filtran en la bitácora junto con
# su search.finished.
AUDIT_ENTITY = "search"

_SELECT_SUMMARY = text(
    """
    SELECT executive_summary, llm_provider, llm_model, prompt_version,
           llm_tokens_in, llm_tokens_out, llm_cost_usd
    FROM reports WHERE search_id = :search_id
    """
)
_INSERT_SUMMARY = text(
    """
    INSERT INTO reports (search_id, executive_summary, llm_provider, llm_model, prompt_version,
        llm_tokens_in, llm_tokens_out, llm_cost_usd, created_by)
    VALUES (:search_id, :text, :provider, :model, :prompt_version,
        :tokens_in, :tokens_out, :cost, :created_by)
    ON CONFLICT (search_id) DO NOTHING
    """
)
_PROVIDER_USAGE = text(
    """
    SELECT provider,
           count(*) AS queries,
           coalesce(sum(results_count), 0) AS results,
           coalesce(sum(cost_credits), 0) AS credits,
           count(*) FILTER (WHERE from_cache) AS from_cache,
           count(*) FILTER (WHERE status = 'error') AS failed
    FROM provider_queries
    WHERE search_id = :search_id
    GROUP BY provider
    ORDER BY provider
    """
)
_INSERT_AUDIT = text(
    "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
    "VALUES (:user_id, :action, :entity_type, :entity_id, "
    "CAST(:payload AS jsonb), CAST(:ip AS inet))"
)


class PostgresReportStore:
    """Resumen guardado, uso de proveedores y bitácora de reportes."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def summary(self, search_id: UUID) -> StoredSummary | None:
        """Ver ``ReportStorePort.summary``."""
        async with self._engine.connect() as conn:
            row = (await conn.execute(_SELECT_SUMMARY, {"search_id": search_id})).mappings().first()
        if row is None:
            return None
        return StoredSummary(
            text=row["executive_summary"],
            provider=row["llm_provider"],
            model=row["llm_model"],
            prompt_version=row["prompt_version"],
            usage=LLMUsage(row["llm_tokens_in"], row["llm_tokens_out"]),
            cost_usd=float(row["llm_cost_usd"]),
        )

    async def set_pdf_path(self, search_id: UUID, path: str) -> bool:
        """Anota dónde quedó el PDF que armó una corrida automática (F12.8).

        Args:
            search_id: Búsqueda.
            path: Ruta del archivo en el servidor.

        Returns:
            ``True`` si la búsqueda ya tenía su fila de reporte (la crea el
            resumen ejecutivo); sin resumen no hay dónde anotarlo.
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("UPDATE reports SET pdf_path = :path WHERE search_id = :id"),
                {"path": path, "id": search_id},
            )
        return result.rowcount > 0

    async def save_summary(self, search_id: UUID, summary: StoredSummary, actor: Actor) -> None:
        """Ver ``ReportStorePort.save_summary``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                _INSERT_SUMMARY,
                {
                    "search_id": search_id,
                    "text": summary.text,
                    "provider": summary.provider,
                    "model": summary.model,
                    "prompt_version": summary.prompt_version,
                    "tokens_in": summary.usage.tokens_in,
                    "tokens_out": summary.usage.tokens_out,
                    "cost": summary.cost_usd,
                    "created_by": actor.user_id,
                },
            )

    async def provider_usage(self, search_id: UUID) -> list[ProviderUsage]:
        """Ver ``ReportStorePort.provider_usage``."""
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_PROVIDER_USAGE, {"search_id": search_id})).mappings()
            return [
                ProviderUsage(
                    provider=r["provider"],
                    queries=int(r["queries"]),
                    results=int(r["results"]),
                    credits=int(r["credits"]),
                    from_cache=int(r["from_cache"]),
                    failed=int(r["failed"]),
                )
                for r in rows
            ]

    async def record_generated(self, search_id: UUID, report_format: str, actor: Actor) -> None:
        """Ver ``ReportStorePort.record_generated``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                _INSERT_AUDIT,
                {
                    "user_id": actor.user_id,
                    "action": REPORT_GENERATED,
                    "entity_type": AUDIT_ENTITY,
                    "entity_id": str(search_id),
                    "payload": json.dumps({"formato": report_format}),
                    "ip": actor.ip,
                },
            )
