"""Envíos contra la base de pruebas (migración 0035, ADR-0039)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.deliveries_repository import PostgresDeliveryStore
from app.application.pagination import TimeCursor
from app.application.ports.deliveries import AttemptRecord, NewDelivery, RuleDraft
from app.core.config import Settings
from app.domain.deliveries import (
    SOURCE_FGR_RUN,
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
    DeliveryStatus,
    RecipientDraft,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 7, 13, 5, tzinfo=UTC)


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        for table in (
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


def new_delivery(account_id: int, recipient_id: int, rule_id: int, key: str) -> NewDelivery:
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
    recipient = await store.create_recipient(RecipientDraft("Benjamin", "benji@hotmail.com", None))
    edited = await store.update_recipient(
        recipient.id, RecipientDraft("Benjamin O.", "benji@hotmail.com", "525512345678")
    )
    rule = await store.create_rule(
        RuleDraft(SOURCE_FGR_RUN, recipient.id, DeliveryChannel.EMAIL, account.id, (7, 15))
    )
    off = await store.update_rule(
        rule.id,
        RuleDraft(SOURCE_FGR_RUN, recipient.id, DeliveryChannel.EMAIL, account.id, (), False),
    )

    assert again.id == account.id and again.label == "Ovitech 2"
    assert (active.status, active.address) == (AccountStatus.ACTIVE, "ovitech_22@hotmail.com")
    assert [a.id for a in await store.list_accounts()] == [account.id]
    assert edited.data.phone == "525512345678"
    assert rule.data.hours == (7, 15)
    assert (off.data.hours, off.data.is_active) == ((), False)
    assert await store.list_rules(SOURCE_FGR_RUN, active_only=True) == []
    assert len(await store.list_rules()) == 1
    assert await store.get_rule(999) is None


async def test_guias_idempotentes_intentos_reintento_e_historial(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresDeliveryStore(test_engine)
    account = await store.save_account(
        AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.ACTIVE
    )
    recipient = await store.create_recipient(RecipientDraft("Benjamin", "benji@hotmail.com", None))
    rule = await store.create_rule(
        RuleDraft(SOURCE_FGR_RUN, recipient.id, DeliveryChannel.EMAIL, account.id, ())
    )

    first = await store.create_deliveries([new_delivery(account.id, recipient.id, rule.id, "k1")])
    repeated = await store.create_deliveries(
        [new_delivery(account.id, recipient.id, rule.id, "k1")]
    )
    assert (len(first), repeated) == (1, [])

    far_future = datetime.now(UTC) + timedelta(days=1)
    [due] = await store.due_deliveries(far_future, 10)
    assert due.recipient_name == "Benjamin"
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
