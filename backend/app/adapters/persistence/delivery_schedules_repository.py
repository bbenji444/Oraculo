"""Envíos programados en PostgreSQL (migración 0043, ADR-0046).

Implementa ``DeliveryScheduleStorePort``. Las tablas tienen seguridad por
filas: con el engine de la API cada persona lee y escribe solo sus envíos; el
worker (sin contexto) los ve todos para lanzar las corridas.

No hace: no valida (eso es el dominio) ni lanza corridas (eso es el worker).
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.application.ports.delivery_schedules import DeliverySchedule
from app.domain.delivery_schedules import ScheduleDraft
from app.domain.errors import DeliveryNotFoundError
from app.domain.schedule import RunSchedule

_SELECT = """
    SELECT s.id, s.owner, s.name, s.concept_ids, s.region_id, s.times, s.days, s.is_active,
           s.updated_at,
           COALESCE(ARRAY(SELECT r.recipient_id FROM delivery_schedule_recipients r
                          WHERE r.schedule_id = s.id ORDER BY r.recipient_id), '{}') AS recipients
    FROM delivery_schedules s
"""
_LIST = text(_SELECT + " ORDER BY s.owner, s.name, s.id")
_GET = text(_SELECT + " WHERE s.id = :id")
_INSERT = text(
    "INSERT INTO delivery_schedules (owner, name, concept_ids, region_id, times, days, "
    "is_active) VALUES (:owner, :name, CAST(:concepts AS bigint[]), :region, "
    "CAST(:times AS smallint[]), CAST(:days AS smallint[]), :active) RETURNING id"
)
_UPDATE = text(
    "UPDATE delivery_schedules SET name = :name, concept_ids = CAST(:concepts AS bigint[]), "
    "region_id = :region, times = CAST(:times AS smallint[]), days = CAST(:days AS smallint[]), "
    "is_active = :active, updated_at = now() WHERE id = :id RETURNING id"
)
_CLEAR_RECIPIENTS = text("DELETE FROM delivery_schedule_recipients WHERE schedule_id = :id")
_ADD_RECIPIENTS = text(
    "INSERT INTO delivery_schedule_recipients (schedule_id, recipient_id) "
    "SELECT :id, unnest(CAST(:recipients AS bigint[])) ON CONFLICT DO NOTHING"
)


def _schedule(row: Row) -> DeliverySchedule:
    return DeliverySchedule(
        id=row.id,
        owner=row.owner,
        data=ScheduleDraft(
            name=row.name,
            concept_ids=tuple(row.concept_ids),
            region_id=row.region_id,
            schedule=RunSchedule(tuple(row.times), tuple(row.days or ())),
            recipient_ids=tuple(row.recipients or ()),
            is_active=row.is_active,
        ),
        updated_at=row.updated_at,
    )


def _params(data: ScheduleDraft) -> dict[str, object]:
    return {
        "name": data.name,
        "concepts": list(data.concept_ids),
        "region": data.region_id,
        "times": list(data.schedule.times),
        "days": list(data.schedule.days),
        "active": data.is_active,
    }


class PostgresDeliveryScheduleStore:
    """``DeliveryScheduleStorePort`` en PostgreSQL."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el motor de la base.

        Args:
            engine: Motor asíncrono (el de la API aplica la seguridad por filas).
        """
        self._engine = engine

    async def list_schedules(self) -> list[DeliverySchedule]:
        """Ver ``DeliveryScheduleStorePort.list_schedules``."""
        async with self._engine.connect() as conn:
            return [_schedule(r) for r in await conn.execute(_LIST)]

    async def get_schedule(self, schedule_id: int) -> DeliverySchedule | None:
        """Ver ``DeliveryScheduleStorePort.get_schedule``."""
        async with self._engine.connect() as conn:
            row = (await conn.execute(_GET, {"id": schedule_id})).first()
        return _schedule(row) if row else None

    async def create_schedule(self, data: ScheduleDraft, owner: str) -> DeliverySchedule:
        """Ver ``DeliveryScheduleStorePort.create_schedule``."""
        async with self._engine.begin() as conn:
            new_id = (await conn.execute(_INSERT, {**_params(data), "owner": owner})).scalar_one()
            await self._set_recipients(conn, new_id, data)
            row = (await conn.execute(_GET, {"id": new_id})).one()
        return _schedule(row)

    async def update_schedule(self, schedule_id: int, data: ScheduleDraft) -> DeliverySchedule:
        """Ver ``DeliveryScheduleStorePort.update_schedule``."""
        async with self._engine.begin() as conn:
            found = (await conn.execute(_UPDATE, {**_params(data), "id": schedule_id})).first()
            if found is None:
                raise DeliveryNotFoundError("No existe ese envío programado.", {"id": schedule_id})
            await conn.execute(_CLEAR_RECIPIENTS, {"id": schedule_id})
            await self._set_recipients(conn, schedule_id, data)
            row = (await conn.execute(_GET, {"id": schedule_id})).one()
        return _schedule(row)

    async def delete_schedule(self, schedule_id: int) -> bool:
        """Ver ``DeliveryScheduleStorePort.delete_schedule``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text("DELETE FROM delivery_schedules WHERE id = :id RETURNING id"),
                    {"id": schedule_id},
                )
            ).first()
        return row is not None

    async def claim_run(self, run_key: str) -> bool:
        """Ver ``DeliveryScheduleStorePort.claim_run``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO delivery_schedule_claims (run_key) VALUES (:key) "
                        "ON CONFLICT DO NOTHING RETURNING run_key"
                    ),
                    {"key": run_key},
                )
            ).first()
        return row is not None

    async def set_topic(self, search_id: UUID, topic: str) -> None:
        """Ver ``DeliveryScheduleStorePort.set_topic``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE searches SET topic_key = :topic WHERE id = :id"),
                {"id": search_id, "topic": topic},
            )

    @staticmethod
    async def _set_recipients(conn: AsyncConnection, schedule_id: int, data: ScheduleDraft) -> None:
        if data.recipient_ids:
            await conn.execute(
                _ADD_RECIPIENTS, {"id": schedule_id, "recipients": list(data.recipient_ids)}
            )
