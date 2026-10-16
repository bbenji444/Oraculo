"""Registro de peticiones a proveedores sobre PostgreSQL (``provider_queries``).

Implementa ``ProviderQueryLogPort`` con SQL explícito. Si la petición la
pidió una persona (el comando de prueba), también deja una fila en
``audit_log``, en la misma transacción, con los créditos gastados
(CLAUDE.md §8).

No hace: no decide presupuesto ni guarda las notas (eso llega en F4).
"""

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.audit import Actor
from app.application.ports.provider_log import ProviderQueryRecord, QueryRun

AUDIT_ACTION = "provider.query_executed"
AUDIT_ENTITY = "provider_query"


class PostgresProviderQueryLog:
    """Escritura y consultas de ``provider_queries``."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def record(self, entry: ProviderQueryRecord, actor: Actor | None = None) -> int:
        """Ver ``ProviderQueryLogPort.record``."""
        async with self._engine.begin() as conn:
            row_id: int = (
                await conn.execute(
                    text(
                        """
                        INSERT INTO provider_queries (search_id, provider, query_text, params,
                            status, http_status, results_count, from_cache, cost_credits,
                            duration_ms, error_message)
                        VALUES (:search_id, :provider, :query_text, CAST(:params AS jsonb),
                            :status, :http_status, :results_count, :from_cache, :cost_credits,
                            :duration_ms, :error_message)
                        RETURNING id
                        """
                    ),
                    {
                        "search_id": entry.search_id,
                        "provider": entry.provider,
                        "query_text": entry.query_text,
                        "params": json.dumps(dict(entry.params), ensure_ascii=False),
                        "status": entry.status,
                        "http_status": entry.http_status,
                        "results_count": entry.results_count,
                        "from_cache": entry.from_cache,
                        "cost_credits": entry.cost_credits,
                        "duration_ms": entry.duration_ms,
                        "error_message": entry.error_message,
                    },
                )
            ).scalar_one()
            if actor is not None:
                payload = {
                    "proveedor": entry.provider,
                    "consulta": entry.query_text,
                    "estado": entry.status,
                    "resultados": entry.results_count,
                    "creditos": entry.cost_credits,
                }
                await conn.execute(
                    text(
                        "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, "
                        "ip) VALUES (:user_id, :action, :entity_type, :entity_id, "
                        "CAST(:payload AS jsonb), CAST(:ip AS inet))"
                    ),
                    {
                        "user_id": actor.user_id,
                        "action": AUDIT_ACTION,
                        "entity_type": AUDIT_ENTITY,
                        "entity_id": str(row_id),
                        "payload": json.dumps(payload, ensure_ascii=False),
                        "ip": actor.ip,
                    },
                )
        return row_id

    async def runs_of(self, provider: str, query_text: str) -> list[QueryRun]:
        """Ver ``ProviderQueryLogPort.runs_of``.

        Usa el índice (``provider``, ``created_at``); el texto se filtra
        después, y una consulta de diagnóstico tiene pocas filas.
        """
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT created_at, status, results_count FROM provider_queries "
                    "WHERE provider = :provider AND query_text = :text ORDER BY created_at, id"
                ),
                {"provider": provider, "text": query_text},
            )
            return [QueryRun(r.created_at, r.status, r.results_count) for r in rows]

    async def credits_used_since(self, provider: str, since: datetime) -> int:
        """Ver ``ProviderQueryLogPort.credits_used_since``.

        Usa el índice (``provider``, ``created_at``) de la migración 0007.
        """
        async with self._engine.connect() as conn:
            total = await conn.execute(
                text(
                    "SELECT COALESCE(sum(cost_credits), 0) FROM provider_queries "
                    "WHERE provider = :provider AND created_at >= :since"
                ),
                {"provider": provider, "since": since},
            )
            return int(total.scalar_one())
