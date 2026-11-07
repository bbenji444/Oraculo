"""Horario único de las corridas en PostgreSQL (migración 0037, ADR-0040).

Implementa ``ScheduleStorePort``: la fila única de ``monitor_schedule``, las
horas ya lanzadas (``monitor_schedule_claims``) y el costo promedio de las
corridas automáticas (``searches`` + ``reports``).

No hace: no valida el horario (eso es ``RunSchedule.validated``).
"""

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.audit import AuditEntry
from app.application.ports.schedule import StoredSchedule
from app.domain.schedule import RunSchedule

ENTITY_TYPE = "schedule"
# La fila única del horario (CHECK id = 1).
_SCHEDULE_ID = 1

_SAVE = text(
    "INSERT INTO monitor_schedule (id, times, days, updated_at, updated_by) "
    "VALUES (:id, CAST(:times AS smallint[]), CAST(:days AS smallint[]), now(), :user) "
    "ON CONFLICT (id) DO UPDATE SET times = EXCLUDED.times, days = EXCLUDED.days, "
    "updated_at = now(), updated_by = EXCLUDED.updated_by "
    "RETURNING times, days, updated_at, updated_by"
)
_AUDIT = text(
    "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
    "VALUES (:user_id, :action, :entity_type, :entity_id, CAST(:payload AS jsonb), "
    "CAST(:ip AS inet))"
)
# Usa el índice parcial searches_automatic. El costo de una corrida es su IA
# (extracción, resúmenes, clasificación) más el resumen ejecutivo de su reporte.
_AVERAGE_COST = text(
    "SELECT avg(s.llm_cost_usd + COALESCE(r.cost, 0)) FROM searches s "
    "LEFT JOIN LATERAL (SELECT sum(llm_cost_usd) AS cost FROM reports "
    "WHERE search_id = s.id) r ON true "
    "WHERE s.trigger = 'automatic' AND s.status IN ('completed', 'partial') "
    "AND s.deleted_at IS NULL AND s.created_at >= :since"
)


class PostgresScheduleStore:
    """``ScheduleStorePort`` sobre PostgreSQL."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el motor de la base."""
        self._engine = engine

    async def get(self) -> StoredSchedule | None:
        """Ver ``ScheduleStorePort.get``."""
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT times, days, updated_at, updated_by FROM monitor_schedule "
                        "WHERE id = :id"
                    ),
                    {"id": _SCHEDULE_ID},
                )
            ).first()
        if row is None:
            return None
        return StoredSchedule(
            RunSchedule(tuple(row.times), tuple(row.days)), row.updated_at, row.updated_by
        )

    async def save(self, schedule: RunSchedule, audit: AuditEntry) -> StoredSchedule:
        """Ver ``ScheduleStorePort.save``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    _SAVE,
                    {
                        "id": _SCHEDULE_ID,
                        "times": list(schedule.times),
                        "days": list(schedule.days),
                        "user": audit.actor.user_id,
                    },
                )
            ).one()
            await conn.execute(
                _AUDIT,
                {
                    "user_id": audit.actor.user_id,
                    "action": audit.action,
                    "entity_type": ENTITY_TYPE,
                    "entity_id": str(_SCHEDULE_ID),
                    "payload": json.dumps(dict(audit.payload), ensure_ascii=False),
                    "ip": audit.actor.ip,
                },
            )
        return StoredSchedule(
            RunSchedule(tuple(row.times), tuple(row.days)), row.updated_at, row.updated_by
        )

    async def claim(self, slot: datetime) -> bool:
        """Ver ``ScheduleStorePort.claim``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO monitor_schedule_claims (slot) VALUES (:slot) "
                        "ON CONFLICT (slot) DO NOTHING RETURNING slot"
                    ),
                    {"slot": slot},
                )
            ).first()
        return row is not None

    async def average_run_cost(self, since: datetime) -> float | None:
        """Ver ``ScheduleStorePort.average_run_cost``."""
        async with self._engine.connect() as conn:
            value = (await conn.execute(_AVERAGE_COST, {"since": since})).scalar()
        return float(value) if value is not None else None
