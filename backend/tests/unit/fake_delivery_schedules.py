"""Envíos programados en memoria, para probar sin base (ADR-0046)."""

from dataclasses import replace
from uuid import UUID

from app.application.ports.delivery_schedules import DeliverySchedule
from app.domain.delivery_schedules import ScheduleDraft


class FakeDeliveryScheduleStore:
    """``DeliveryScheduleStorePort`` en un diccionario.

    ``visible_to`` imita la seguridad por filas: con un ``username``, solo se
    ven sus envíos; con ``None`` (el worker o el superusuario), todos.
    """

    def __init__(self) -> None:
        self.schedules: dict[int, DeliverySchedule] = {}
        self.claims: set[str] = set()
        self.topics: dict[UUID, str] = {}
        self.visible_to: str | None = None

    def _sees(self, schedule: DeliverySchedule) -> bool:
        return self.visible_to is None or schedule.owner == self.visible_to

    async def list_schedules(self) -> list[DeliverySchedule]:
        return sorted(
            (s for s in self.schedules.values() if self._sees(s)),
            key=lambda s: (s.owner, s.data.name, s.id),
        )

    async def get_schedule(self, schedule_id: int) -> DeliverySchedule | None:
        found = self.schedules.get(schedule_id)
        return found if found and self._sees(found) else None

    async def create_schedule(self, data: ScheduleDraft, owner: str) -> DeliverySchedule:
        schedule = DeliverySchedule(len(self.schedules) + 1, owner, data)
        self.schedules[schedule.id] = schedule
        return schedule

    async def update_schedule(self, schedule_id: int, data: ScheduleDraft) -> DeliverySchedule:
        updated = replace(self.schedules[schedule_id], data=data)
        self.schedules[schedule_id] = updated
        return updated

    async def delete_schedule(self, schedule_id: int) -> bool:
        if await self.get_schedule(schedule_id) is None:
            return False
        del self.schedules[schedule_id]
        return True

    async def claim_run(self, run_key: str) -> bool:
        if run_key in self.claims:
            return False
        self.claims.add(run_key)
        return True

    async def set_topic(self, search_id: UUID, topic: str) -> None:
        self.topics[search_id] = topic
