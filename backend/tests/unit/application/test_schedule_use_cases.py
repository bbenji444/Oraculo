"""Casos de uso del horario único de las corridas (ADR-0040), con un almacén en memoria."""

from datetime import UTC, datetime, timedelta

import pytest

from app.application.audit import SCHEDULE_UPDATED, Actor, AuditEntry
from app.application.clock import MEXICO_CITY
from app.application.ports.schedule import StoredSchedule
from app.application.use_cases.schedule import DueRun, GetSchedule, UpdateSchedule
from app.domain.errors import ScheduleValidationError
from app.domain.schedule import RunSchedule

pytestmark = pytest.mark.anyio

DEFAULT = RunSchedule.from_hours((7, 15, 23))
# 06/11/2026 a las 14:00 de la CDMX.
NOW = datetime(2026, 11, 6, 20, 0, tzinfo=UTC)
GRACE = timedelta(minutes=10)


class FakeScheduleStore:
    """``ScheduleStorePort`` en memoria."""

    def __init__(self, cost: float | None = 0.038) -> None:
        self.stored: StoredSchedule | None = None
        self.audits: list[AuditEntry] = []
        self.claimed: set[datetime] = set()
        self.cost = cost

    async def get(self) -> StoredSchedule | None:
        return self.stored

    async def save(self, schedule: RunSchedule, audit: AuditEntry) -> StoredSchedule:
        self.stored = StoredSchedule(schedule, NOW, audit.actor.user_id)
        self.audits.append(audit)
        return self.stored

    async def claim(self, slot: datetime) -> bool:
        if slot in self.claimed:
            return False
        self.claimed.add(slot)
        return True

    async def average_run_cost(self, since: datetime) -> float | None:
        return self.cost


def reader(store: FakeScheduleStore) -> GetSchedule:
    return GetSchedule(store, DEFAULT, lambda: NOW)


def cdmx(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=MEXICO_CITY)


async def test_sin_horario_guardado_vale_el_del_env() -> None:
    view = await reader(FakeScheduleStore()).execute()

    assert (view.schedule, view.is_default, view.updated_by) == (DEFAULT, True, None)
    assert view.upcoming[:3] == [cdmx(6, 15), cdmx(6, 23), cdmx(7, 7)]
    assert view.average_run_cost_usd == 0.038


async def test_el_admin_agrega_una_hora_y_aplica_a_todos() -> None:
    store = FakeScheduleStore()

    view = await UpdateSchedule(store, reader(store)).execute(
        (420, 900, 1140, 1380), (), Actor("benji", "127.0.0.1")
    )

    assert (view.schedule.times, view.is_default, view.updated_by) == (
        (420, 900, 1140, 1380),
        False,
        "benji",
    )
    assert view.upcoming[:2] == [cdmx(6, 15), cdmx(6, 19)]
    [audit] = store.audits
    assert audit.action == SCHEDULE_UPDATED
    assert audit.payload == {
        "before": {"times": ["07:00", "15:00", "23:00"], "days": []},
        "after": {"times": ["07:00", "15:00", "19:00", "23:00"], "days": []},
    }


async def test_un_horario_que_rompe_los_topes_no_se_guarda() -> None:
    store = FakeScheduleStore()

    with pytest.raises(ScheduleValidationError):
        await UpdateSchedule(store, reader(store)).execute((420, 450), (), Actor("benji"))
    assert (store.stored, store.audits) == (None, [])


async def test_el_reloj_lanza_cada_hora_una_sola_vez() -> None:
    store = FakeScheduleStore()
    due = DueRun(store, reader(store), GRACE)
    three_pm = cdmx(6, 15)

    assert await due.execute(three_pm + timedelta(seconds=20)) == three_pm
    # La siguiente revisión ve la misma hora, pero ya está apartada.
    assert await due.execute(three_pm + timedelta(minutes=1)) is None
    assert await due.execute(cdmx(6, 16)) is None


async def test_el_reloj_usa_el_horario_recien_guardado() -> None:
    store = FakeScheduleStore()
    await UpdateSchedule(store, reader(store)).execute((420, 900, 1140, 1380), (), Actor("benji"))

    assert await DueRun(store, reader(store), GRACE).execute(cdmx(6, 19)) == cdmx(6, 19)


async def test_sin_corridas_no_hay_costo() -> None:
    assert (await reader(FakeScheduleStore(cost=None)).execute()).average_run_cost_usd is None
