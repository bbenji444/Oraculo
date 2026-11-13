"""Envíos contra la base de pruebas (migraciones 0035 a 0042, ADR-0039, ADR-0040 y ADR-0045)."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.access_scope import as_user, create_api_engine
from app.adapters.persistence.deliveries_repository import PostgresDeliveryStore
from app.adapters.persistence.delivery_schedules_repository import (
    PostgresDeliveryScheduleStore,
)
from app.application.pagination import TimeCursor
from app.application.ports.deliveries import AttemptRecord, NewDelivery, RuleDraft
from app.core.config import Settings
from app.domain.access import AuthUser, Role
from app.domain.deliveries import (
    DEFAULT_OWNER,
    SOURCE_FGR_RUN,
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
    DeliveryStatus,
    RecipientDraft,
)
from app.domain.delivery_schedules import ScheduleDraft
from app.domain.errors import DeliveryNotFoundError
from app.domain.schedule import RunSchedule
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 7, 13, 5, tzinfo=UTC)


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        for table in (
            "delivery_schedule_claims",
            "delivery_schedule_recipients",
            "delivery_schedules",
            "delivery_attempts",
            "deliveries",
            "delivery_rules",
            "delivery_recipients",
            "delivery_accounts",
        ):
            conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608 — nombres fijos de la prueba


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


def rule_draft(account_id: int, *, is_active: bool = True) -> RuleDraft:
    return RuleDraft(
        source=SOURCE_FGR_RUN,
        channel=DeliveryChannel.EMAIL,
        account_id=account_id,
        is_active=is_active,
    )


def new_delivery(
    account_id: int,
    recipient_id: int,
    rule_id: int,
    key: str,
    scheduled_for: datetime | None = None,
) -> NewDelivery:
    return NewDelivery(
        id=uuid4(),
        rule_id=rule_id,
        source=SOURCE_FGR_RUN,
        source_ref="corrida-1",
        channel=DeliveryChannel.EMAIL,
        account_id=account_id,
        recipient_id=recipient_id,
        destination="benji@hotmail.com",
        subject="Reporte FGR",
        attachment_name="fgr.pdf",
        idempotency_key=key,
        scheduled_for=scheduled_for,
    )


async def test_cuentas_destinatarios_y_reglas(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresDeliveryStore(test_engine)

    account = await store.save_account(
        AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.PENDING
    )
    again = await store.save_account(
        AccountProvider.OUTLOOK, "Ovitech 2", "ca_1", AccountStatus.PENDING
    )
    active = await store.update_account(account.id, AccountStatus.ACTIVE, "ovitech_22@hotmail.com")
    recipient = await store.create_recipient(
        RecipientDraft("Benjamin", "benji@hotmail.com", None), "benji"
    )
    edited = await store.update_recipient(
        recipient.id, RecipientDraft("Benjamin O.", "benji@hotmail.com", "525512345678")
    )
    rule = await store.save_rule(rule_draft(account.id))
    # Una sola regla por fuente y canal: guardar otra vez la reemplaza.
    off = await store.save_rule(rule_draft(account.id, is_active=False))

    assert again.id == account.id and again.label == "Ovitech 2"
    assert (active.status, active.address) == (AccountStatus.ACTIVE, "ovitech_22@hotmail.com")
    assert [a.id for a in await store.list_accounts()] == [account.id]
    assert edited.data.phone == "525512345678"
    assert (off.id, rule.data.is_active, off.data.is_active) == (rule.id, True, False)
    assert await store.list_rules(SOURCE_FGR_RUN, active_only=True) == []
    assert len(await store.list_rules()) == 1

    assert await store.delete_recipient(recipient.id)
    assert not await store.delete_recipient(recipient.id)


async def test_guias_idempotentes_intentos_reintento_e_historial(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresDeliveryStore(test_engine)
    account = await store.save_account(
        AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.ACTIVE
    )
    recipient = await store.create_recipient(
        RecipientDraft("Benjamin", "benji@hotmail.com", None), "benji"
    )
    rule = await store.save_rule(rule_draft(account.id))

    first = await store.create_deliveries(
        [new_delivery(account.id, recipient.id, rule.id, "k1", NOW)]
    )
    repeated = await store.create_deliveries(
        [new_delivery(account.id, recipient.id, rule.id, "k1")]
    )
    assert (len(first), repeated) == (1, [])

    far_future = datetime.now(UTC) + timedelta(days=1)
    [due] = await store.due_deliveries(far_future, 10)
    assert (due.recipient_name, due.scheduled_for) == ("Benjamin", NOW)
    assert await store.claim(due.id)
    assert not await store.claim(due.id)  # ya la tomó otra pasada

    await store.record_attempt(
        AttemptRecord(due.id, 1, False, None, "Composio: timeout", NOW, NOW),
        DeliveryStatus.FAILED,
        None,
        None,
    )
    assert await store.reset_for_retry(due.id, NOW)
    assert await store.claim(due.id)
    await store.record_attempt(
        AttemptRecord(due.id, 2, True, "202", None, NOW, NOW), DeliveryStatus.SENT, None, "msg-1"
    )

    sent = await store.get_delivery(due.id)
    assert sent is not None
    assert (sent.status, sent.attempts, sent.provider_ref, sent.last_error) == (
        DeliveryStatus.SENT,
        2,
        "msg-1",
        None,
    )
    assert sent.sent_at is not None
    assert [a.ok for a in await store.attempts_of(due.id)] == [False, True]
    page = await store.history(None, 10)
    assert [d.id for d in page] == [due.id]
    assert await store.history(TimeCursor(page[0].created_at, str(page[0].id)), 10) == []


async def test_solo_las_que_llevan_rato_enviando_estan_atoradas(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    """12/11/2026: un reinicio de la VM dejó una guía «enviando» para siempre."""
    store = PostgresDeliveryStore(test_engine)
    account = await store.save_account(
        AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.ACTIVE
    )
    recipient = await store.create_recipient(
        RecipientDraft("Geovanni", "geo@example.com", None), "benji"
    )
    rule = await store.save_rule(rule_draft(account.id))
    old, fresh = await store.create_deliveries(
        [
            new_delivery(account.id, recipient.id, rule.id, "atorada", NOW),
            new_delivery(account.id, recipient.id, rule.id, "saliendo", NOW),
        ]
    )
    assert await store.claim(old)
    assert await store.claim(fresh)
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE deliveries SET updated_at = now() - interval '20 minutes' WHERE id = :id"),
            {"id": old},
        )

    stuck = await store.stuck_deliveries(datetime.now(UTC) - timedelta(minutes=15))

    assert [d.id for d in stuck] == [old]
    assert stuck[0].status is DeliveryStatus.SENDING


# --- Envíos por usuario: dueño, horas y seguridad por filas (migración 0042, ADR-0045) ---

ANA = AuthUser(911, "rls-envios-ana", "Ana", Role.USER)
PEPE = AuthUser(912, "rls-envios-pepe", "Pepe", Role.USER)
JEFA = AuthUser(913, "rls-envios-jefa", "Jefa", Role.SUPERUSER)


@pytest.fixture
async def api_engine(settings: Settings, sync_engine: Engine) -> AsyncIterator[AsyncEngine]:
    engine = create_api_engine(settings.database_url(test=True))
    yield engine
    await engine.dispose()


async def test_cada_persona_ve_y_cambia_solo_sus_correos(
    sync_engine: Engine, test_engine: AsyncEngine, api_engine: AsyncEngine
) -> None:
    store = PostgresDeliveryStore(api_engine)
    with as_user(ANA):
        mine = await store.create_recipient(RecipientDraft("Ana", "ana@x.mx", None), ANA.username)
    with as_user(PEPE):
        await store.create_recipient(RecipientDraft("Pepe", "pepe@x.mx", None), PEPE.username)
        # Pepe no ve, no edita ni borra el de Ana.
        assert [r.data.email for r in await store.list_recipients()] == ["pepe@x.mx"]
        assert await store.get_recipient(mine.id) is None
        with pytest.raises(DeliveryNotFoundError):
            await store.update_recipient(mine.id, RecipientDraft("X", "x@x.mx", None))
        assert not await store.delete_recipient(mine.id)
        # Ni puede dar de alta uno a nombre de otra persona.
        with pytest.raises(DBAPIError, match="row-level security"):
            await store.create_recipient(RecipientDraft("Falso", "f@x.mx", None), ANA.username)
    with as_user(ANA):
        [own] = await store.list_recipients()
    with as_user(JEFA):
        everyone = {r.owner for r in await store.list_recipients()}
    # Sin contexto (anónimo) no se ve nada.
    assert await store.list_recipients() == []

    assert own.owner == ANA.username
    assert everyone == {ANA.username, PEPE.username}
    # El worker (sin contexto en su engine) ve a todos para mandar la corrida.
    assert len(await PostgresDeliveryStore(test_engine).list_recipients()) == 2


async def test_cada_envio_es_del_dueno_del_correo_y_solo_el_lo_ve(
    sync_engine: Engine, test_engine: AsyncEngine, api_engine: AsyncEngine
) -> None:
    worker = PostgresDeliveryStore(test_engine)
    account = await worker.save_account(
        AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.ACTIVE
    )
    rule = await worker.save_rule(rule_draft(account.id))
    ana = await worker.create_recipient(RecipientDraft("Ana", "ana@x.mx", None), ANA.username)
    pepe = await worker.create_recipient(RecipientDraft("Pepe", "pepe@x.mx", None), PEPE.username)
    # Como el worker: sin dueño explícito, la base toma el del destinatario.
    await worker.create_deliveries(
        [
            new_delivery(account.id, ana.id, rule.id, "k-ana"),
            new_delivery(account.id, pepe.id, rule.id, "k-pepe"),
        ]
    )

    store = PostgresDeliveryStore(api_engine)
    with as_user(ANA):
        mine = await store.history(None, 10)
    with as_user(PEPE):
        theirs = await store.history(None, 10)
        assert await store.get_delivery(mine[0].id) is None
        assert not await store.claim(mine[0].id)
    with as_user(JEFA):
        everything = await store.history(None, 10)

    assert [(d.recipient_name, d.owner) for d in mine] == [("Ana", ANA.username)]
    assert [d.owner for d in theirs] == [PEPE.username]
    assert len(everything) == 2


async def test_lo_que_existia_queda_a_nombre_de_benji(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    async with test_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO delivery_recipients (name, email) VALUES ('Viejo', 'v@x.mx')")
        )
    [old] = await PostgresDeliveryStore(test_engine).list_recipients()

    assert old.owner == DEFAULT_OWNER


# --- Envíos programados (migración 0043, ADR-0046) ---


@pytest.fixture
def region_id(sync_engine: Engine, settings: Settings, tmp_path: Path) -> int:
    load_fixture_catalog(sync_engine, settings, tmp_path)
    with sync_engine.connect() as conn:
        return int(conn.execute(text("SELECT id FROM regions ORDER BY id LIMIT 1")).scalar_one())


def _schedule(region: int, times: tuple[int, ...], recipients: tuple[int, ...]) -> ScheduleDraft:
    return ScheduleDraft("Extorsión tarde", (3, 7), region, RunSchedule(times, (1, 5)), recipients)


async def test_envios_programados_de_cada_persona(
    sync_engine: Engine, test_engine: AsyncEngine, api_engine: AsyncEngine, region_id: int
) -> None:
    recipients = PostgresDeliveryStore(api_engine)
    schedules = PostgresDeliveryScheduleStore(api_engine)
    with as_user(ANA):
        mail = await recipients.create_recipient(
            RecipientDraft("Ana", "ana@x.mx", None), "rls-envios-ana"
        )
        saved = await schedules.create_schedule(
            _schedule(region_id, (960, 1200), (mail.id,)), ANA.username
        )
        edited = await schedules.update_schedule(saved.id, _schedule(region_id, (1000,), ()))
    with as_user(PEPE):
        assert await schedules.list_schedules() == []
        assert await schedules.get_schedule(saved.id) is None
        assert not await schedules.delete_schedule(saved.id)
        with pytest.raises(DBAPIError, match="row-level security"):
            await schedules.create_schedule(_schedule(region_id, (960,), ()), ANA.username)
    with as_user(JEFA):
        assert [s.owner for s in await schedules.list_schedules()] == [ANA.username]
    worker = PostgresDeliveryScheduleStore(test_engine)

    assert (saved.data.schedule.times, saved.data.schedule.days) == ((960, 1200), (1, 5))
    assert (saved.data.concept_ids, saved.data.recipient_ids) == ((3, 7), (mail.id,))
    assert (edited.data.schedule.times, edited.data.recipient_ids) == ((1000,), ())
    assert [s.id for s in await worker.list_schedules()] == [saved.id]
    # Cada corrida se aparta una sola vez, aunque dos revisiones lleguen juntas.
    assert await worker.claim_run("c=3,7|r=1|2026-11-11T12:00|2026-11-11T16:00")
    assert not await worker.claim_run("c=3,7|r=1|2026-11-11T12:00|2026-11-11T16:00")
    with as_user(ANA):
        assert await schedules.delete_schedule(saved.id)
