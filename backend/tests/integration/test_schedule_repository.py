"""Horario único de las corridas contra la base de pruebas (migración 0037, ADR-0040)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.schedule_repository import PostgresScheduleStore
from app.application.audit import SCHEDULE_UPDATED, Actor, AuditEntry
from app.core.config import Settings
from app.domain.schedule import RunSchedule

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
SLOT = datetime(2026, 11, 6, 21, 0, tzinfo=UTC)
USER = "prueba-horario"


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM monitor_schedule_claims"))
        conn.execute(text("DELETE FROM monitor_schedule"))
        conn.execute(text("DELETE FROM audit_log WHERE user_id = :u"), {"u": USER})


@pytest.fixture
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    _empty(engine)
    yield engine
    _empty(engine)
    engine.dispose()


async def test_guardar_el_horario_deja_su_bitacora(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresScheduleStore(test_engine)
    assert await store.get() is None

    first = await store.save(
        RunSchedule((420, 900, 1380)), AuditEntry(Actor(USER), SCHEDULE_UPDATED, {"n": 1})
    )
    second = await store.save(
        RunSchedule((420, 900, 1140, 1380), (1, 2, 3, 4, 5)),
        AuditEntry(Actor(USER, "127.0.0.1"), SCHEDULE_UPDATED, {"n": 2}),
    )
    stored = await store.get()

    assert first.schedule.times == (420, 900, 1380)
    assert stored is not None and stored.schedule == second.schedule
    assert (stored.schedule.days, stored.updated_by) == ((1, 2, 3, 4, 5), USER)
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, entity_type, payload->>'n' FROM audit_log "
                "WHERE user_id = :u ORDER BY id"
            ),
            {"u": USER},
        ).all()
    assert [tuple(r) for r in rows] == [
        (SCHEDULE_UPDATED, "schedule", "1"),
        (SCHEDULE_UPDATED, "schedule", "2"),
    ]


async def test_cada_hora_programada_se_aparta_una_sola_vez(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresScheduleStore(test_engine)

    assert await store.claim(SLOT)
    assert not await store.claim(SLOT)
    assert await store.claim(SLOT + timedelta(hours=4))


async def test_el_costo_promedio_solo_cuenta_corridas_recientes(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresScheduleStore(test_engine)
    # En el futuro no hay corridas: no hay promedio.
    assert await store.average_run_cost(datetime.now(UTC) + timedelta(days=1)) is None
    value = await store.average_run_cost(datetime(2000, 1, 1, tzinfo=UTC))
    assert value is None or value >= 0
