"""Casos de uso de los envíos (ADR-0039), con piezas en memoria."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.application.ports.deliveries import RemoteAccount, RuleDraft, SendResult
from app.application.use_cases.deliveries import (
    ManageAccounts,
    ManageRecipients,
    ManageRules,
    PlanDeliveries,
    RetryDelivery,
    SendDeliveries,
    SendTest,
)
from app.domain.deliveries import (
    SOURCE_FGR_RUN,
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
    DeliveryStatus,
    RuleAudience,
)
from app.domain.errors import (
    DeliveryChannelUnavailableError,
    DeliveryNotFoundError,
    DeliveryValidationError,
)
from tests.unit.fake_deliveries import (
    NOW,
    FakeConnector,
    FakeDeliveryStore,
    FakeReports,
    FakeSender,
)

pytestmark = pytest.mark.anyio


# Horas de la Ciudad de México (UTC-6) expresadas en UTC.
AT_0700 = datetime(2026, 11, 6, 13, 0, tzinfo=UTC)
AT_0930 = datetime(2026, 11, 6, 15, 30, tzinfo=UTC)
AT_1500 = datetime(2026, 11, 6, 21, 0, tzinfo=UTC)
AT_2300 = datetime(2026, 11, 7, 5, 0, tzinfo=UTC)
RUN_MINUTES = frozenset({420, 900, 1380})


def draft(
    times: tuple[int, ...] = (420, 900),
    *,
    audience: RuleAudience = RuleAudience.SELECTED,
    recipient_ids: tuple[int, ...] = (1,),
    exclude_ids: tuple[int, ...] = (),
    days: tuple[int, ...] = (),
    channel: DeliveryChannel = DeliveryChannel.EMAIL,
    account_id: int | None = 1,
    source: str = SOURCE_FGR_RUN,
    name: str = "Regla",
    is_active: bool = True,
) -> RuleDraft:
    return RuleDraft(
        source=source,
        name=name,
        audience=audience,
        recipient_ids=recipient_ids,
        exclude_ids=exclude_ids,
        channel=channel,
        account_id=account_id,
        times=times,
        days=days,
        is_active=is_active,
    )


async def store_with_rule(rule: RuleDraft | None = None) -> FakeDeliveryStore:
    store = FakeDeliveryStore()
    await store.save_account(AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.ACTIVE)
    await ManageRecipients(store).create("Benjamin", "benji@hotmail.com", None)
    await ManageRules(store).create(rule or draft())
    return store


def sender_for(
    store: FakeDeliveryStore, *results: SendResult, pdf: Path | None = None
) -> tuple[SendDeliveries, FakeSender]:
    fake = FakeSender(*results)
    use = SendDeliveries(
        store, FakeReports(pdf=pdf), {DeliveryChannel.EMAIL: fake}, now=lambda: NOW
    )
    return use, fake


async def test_la_corrida_crea_una_guia_por_regla_que_le_toca_y_no_repite() -> None:
    store = await store_with_rule(draft((420, 900)))
    plan = PlanDeliveries(store, FakeReports())

    first = await plan.for_run(SOURCE_FGR_RUN, "corrida-1", AT_1500)
    again = await plan.for_run(SOURCE_FGR_RUN, "corrida-1", AT_1500)
    night = await plan.for_run(SOURCE_FGR_RUN, "corrida-1", AT_2300)

    assert len(first) == 1
    assert (again, night) == ([], [])
    [delivery] = store.deliveries.values()
    assert (delivery.destination, delivery.subject) == (
        "benji@hotmail.com",
        "Reporte FGR · corrida 06/11/2026, 15:00 (CDMX)",
    )


async def test_destinatario_apagado_o_corrida_inexistente_no_crean_guias() -> None:
    store = await store_with_rule()
    await ManageRecipients(store).update(1, "Benjamin", "benji@hotmail.com", None, False)
    plan = PlanDeliveries(store, FakeReports())

    assert await plan.for_run(SOURCE_FGR_RUN, "corrida-1", AT_0700) == []
    assert await plan.for_run(SOURCE_FGR_RUN, "otra", AT_0700) == []


async def test_manda_con_el_pdf_y_queda_enviado(tmp_path: Path) -> None:
    pdf = tmp_path / "fgr.pdf"
    pdf.write_bytes(b"%PDF")
    store = await store_with_rule()
    await PlanDeliveries(store, FakeReports(pdf=pdf)).for_run(SOURCE_FGR_RUN, "corrida-1", AT_0700)
    use, fake = sender_for(store, SendResult(True, "202", "msg-1"), pdf=pdf)

    report = await use.send_due()

    assert (report.attempted, report.sent, report.failed) == (1, 1, 0)
    assert fake.sent[0].attachment == pdf
    [delivery] = store.deliveries.values()
    assert (delivery.status, delivery.attempts, delivery.provider_ref) == (
        DeliveryStatus.SENT,
        1,
        "msg-1",
    )
    assert store.attempts[0].ok


async def test_un_fallo_pasajero_se_reintenta_y_uno_permanente_no() -> None:
    store = await store_with_rule()
    await PlanDeliveries(store, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", AT_0700)
    use, _ = sender_for(store, SendResult(False, error="Composio: timeout", retryable=True))

    await use.send_due()

    [delivery] = store.deliveries.values()
    assert delivery.status is DeliveryStatus.PENDING
    assert delivery.last_error == "Composio: timeout"
    assert delivery.next_attempt_at is not None and delivery.next_attempt_at > NOW

    store2 = await store_with_rule()
    await PlanDeliveries(store2, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", AT_0700)
    use2, _ = sender_for(store2, SendResult(False, error="401 unauthorized", retryable=False))
    await use2.send_due()
    [failed] = store2.deliveries.values()
    assert (failed.status, failed.next_attempt_at) == (DeliveryStatus.FAILED, None)


async def test_sin_llave_o_sin_cuenta_activa_falla_sin_intentar_el_proveedor() -> None:
    store = await store_with_rule()
    await PlanDeliveries(store, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", AT_0700)
    fake = FakeSender(configured=False)
    use = SendDeliveries(store, FakeReports(), {DeliveryChannel.EMAIL: fake}, now=lambda: NOW)

    await use.send_due()

    [delivery] = store.deliveries.values()
    assert delivery.status is DeliveryStatus.FAILED
    assert "COMPOSIO_API_KEY" in (delivery.last_error or "")
    assert fake.sent == []


async def test_mandar_prueba_y_reintentar() -> None:
    store = await store_with_rule()
    use, _ = sender_for(
        store, SendResult(False, error="403 forbidden", retryable=False), SendResult(True, "202")
    )

    failed = await SendTest(store, FakeReports(), use).execute(SOURCE_FGR_RUN, 1, 1)
    assert (failed.is_test, failed.status) == (True, DeliveryStatus.FAILED)

    retried = await RetryDelivery(store, use).execute(failed.id)
    assert (retried.status, retried.attempts) == (DeliveryStatus.SENT, 2)
    assert len(await store.attempts_of(failed.id)) == 2

    with pytest.raises(DeliveryValidationError, match="Solo se reintenta"):
        await RetryDelivery(store, use).execute(failed.id)


async def test_prueba_sin_corrida_o_sin_destinatario() -> None:
    store = await store_with_rule()
    use, _ = sender_for(store)

    with pytest.raises(DeliveryNotFoundError, match="corrida"):
        await SendTest(store, FakeReports(ref=None), use).execute(SOURCE_FGR_RUN, 1, 1)
    with pytest.raises(DeliveryNotFoundError):
        await SendTest(store, FakeReports(), use).execute(SOURCE_FGR_RUN, 99, 1)


async def test_reglas_invalidas() -> None:
    store = await store_with_rule()
    rules = ManageRules(store)

    with pytest.raises(DeliveryValidationError, match="al menos un destinatario"):
        await rules.create(draft(recipient_ids=(99,)))
    with pytest.raises(DeliveryValidationError, match="cuenta de correo"):
        await rules.create(draft(account_id=None))
    with pytest.raises(DeliveryValidationError, match="fuente"):
        await rules.create(draft(source="otra.cosa"))
    with pytest.raises(DeliveryValidationError, match="WhatsApp"):
        await rules.create(draft(channel=DeliveryChannel.WHATSAPP))
    with pytest.raises(DeliveryValidationError, match="nombre"):
        await rules.create(draft(name="   "))
    with pytest.raises(DeliveryValidationError, match="al menos una hora"):
        await rules.create(draft(()))
    with pytest.raises(DeliveryNotFoundError):
        await rules.update(99, draft())
    with pytest.raises(DeliveryNotFoundError):
        await rules.delete(99)


async def test_editar_y_borrar_una_regla() -> None:
    store = await store_with_rule()
    rules = ManageRules(store)

    edited = await rules.update(
        1, draft((1380, 420, 1380), name="  Noche  y mañana ", days=(5, 1), is_active=False)
    )
    assert (edited.data.name, edited.data.times, edited.data.days, edited.data.is_active) == (
        "Noche y mañana",
        (420, 1380),
        (1, 5),
        False,
    )
    await rules.delete(1)
    assert await store.list_rules(SOURCE_FGR_RUN) == []


async def test_la_regla_general_manda_a_todos_menos_los_excluidos() -> None:
    store = await store_with_rule()
    recipients = ManageRecipients(store)
    await recipients.create("Geovanni", "geo@x.mx", None)
    await recipients.create("Tadeo", "tadeo@x.mx", None)
    await recipients.create("Solo WhatsApp", None, "525512345678")
    rule = await ManageRules(store).update(
        1, draft(audience=RuleAudience.ALL, recipient_ids=(1,), exclude_ids=(2, 99))
    )
    # En una regla general la lista de elegidos sobra y la exclusión desconocida se cae.
    assert (rule.data.recipient_ids, rule.data.exclude_ids) == ((), (2,))

    await PlanDeliveries(store, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", AT_1500)

    assert sorted(d.destination for d in store.deliveries.values()) == [
        "benji@hotmail.com",
        "tadeo@x.mx",
    ]


async def test_una_hora_sin_corrida_manda_el_ultimo_reporte_una_vez() -> None:
    store = await store_with_rule(draft((570,), days=(5,)))
    plan = PlanDeliveries(store, FakeReports())
    next_friday = datetime(2026, 11, 13, 15, 30, tzinfo=UTC)
    saturday = datetime(2026, 11, 7, 15, 30, tzinfo=UTC)

    first = await plan.scheduled(SOURCE_FGR_RUN, AT_0930, RUN_MINUTES)
    again = await plan.scheduled(SOURCE_FGR_RUN, AT_0930, RUN_MINUTES)
    later = await plan.scheduled(SOURCE_FGR_RUN, next_friday, RUN_MINUTES)
    weekend = await plan.scheduled(SOURCE_FGR_RUN, saturday, RUN_MINUTES)

    assert (len(first), again, len(later), weekend) == (1, [], 1, [])
    keys = sorted(store.keys)
    assert keys[0].endswith("|2026-11-06 09:30")
    assert keys[1].endswith("|2026-11-13 09:30")
    assert {d.scheduled_for for d in store.deliveries.values()} == {AT_0930, next_friday}


async def test_a_la_hora_de_una_corrida_no_se_adelanta_al_reporte_nuevo() -> None:
    store = await store_with_rule(draft((420, 570)))

    assert (
        await PlanDeliveries(store, FakeReports()).scheduled(SOURCE_FGR_RUN, AT_0700, RUN_MINUTES)
        == []
    )
    assert (
        await PlanDeliveries(store, FakeReports(ref=None)).scheduled(
            SOURCE_FGR_RUN, AT_0930, RUN_MINUTES
        )
        == []
    )


async def test_borrar_un_destinatario() -> None:
    store = await store_with_rule()
    await ManageRecipients(store).delete(1)

    assert await store.list_recipients() == []
    with pytest.raises(DeliveryNotFoundError):
        await ManageRecipients(store).delete(1)


async def test_conectar_y_revisar_cuentas() -> None:
    store = FakeDeliveryStore()
    accounts = ManageAccounts(store, FakeConnector())

    account, url = await accounts.connect(AccountProvider.GMAIL, "  Reportes  ")
    assert (account.status, account.label, url) == (
        AccountStatus.PENDING,
        "Reportes",
        "https://connect.composio.dev/link/lk_prueba",
    )
    refreshed = await accounts.refresh(account.id)
    assert (refreshed.status, refreshed.address) == (AccountStatus.ACTIVE, "ovitech_22@hotmail.com")

    with pytest.raises(DeliveryChannelUnavailableError, match="WhatsApp"):
        await accounts.connect(AccountProvider.WHATSAPP, "x")
    with pytest.raises(DeliveryChannelUnavailableError, match="COMPOSIO_API_KEY"):
        await ManageAccounts(store, FakeConnector(configured=False)).connect(
            AccountProvider.OUTLOOK, "x"
        )
    with pytest.raises(DeliveryValidationError):
        await accounts.connect(AccountProvider.OUTLOOK, "   ")
    with pytest.raises(DeliveryNotFoundError):
        await accounts.refresh(99)


async def test_revisar_una_cuenta_que_sigue_pendiente() -> None:
    store = FakeDeliveryStore()
    pending = RemoteAccount(AccountStatus.PENDING, None)
    accounts = ManageAccounts(store, FakeConnector(remote=pending))
    account, _ = await accounts.connect(AccountProvider.OUTLOOK, "Ovitech")

    assert (await accounts.refresh(account.id)).status is AccountStatus.PENDING


async def test_editar_destinatario_que_no_existe() -> None:
    with pytest.raises(DeliveryNotFoundError):
        await ManageRecipients(FakeDeliveryStore()).update(1, "Ana", "ana@x.mx", None, True)
