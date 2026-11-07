"""Casos de uso de los envíos (ADR-0039), con piezas en memoria."""

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


async def store_with_rule(hours: tuple[int, ...] = (7, 15)) -> FakeDeliveryStore:
    store = FakeDeliveryStore()
    await store.save_account(AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.ACTIVE)
    await ManageRecipients(store).create("Benjamin", "benji@hotmail.com", None)
    await ManageRules(store).create(RuleDraft(SOURCE_FGR_RUN, 1, DeliveryChannel.EMAIL, 1, hours))
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
    store = await store_with_rule((7, 15))
    plan = PlanDeliveries(store, FakeReports())

    first = await plan.for_run(SOURCE_FGR_RUN, "corrida-1", 15)
    again = await plan.for_run(SOURCE_FGR_RUN, "corrida-1", 15)
    night = await plan.for_run(SOURCE_FGR_RUN, "corrida-1", 23)

    assert len(first) == 1
    assert (again, night) == ([], [])
    [delivery] = store.deliveries.values()
    assert (delivery.destination, delivery.subject) == (
        "benji@hotmail.com",
        "Reporte FGR · corrida 06/11/2026, 15:00 (CDMX)",
    )


async def test_destinatario_apagado_o_corrida_inexistente_no_crean_guias() -> None:
    store = await store_with_rule(())
    await ManageRecipients(store).update(1, "Benjamin", "benji@hotmail.com", None, False)

    assert await PlanDeliveries(store, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", 7) == []
    assert await PlanDeliveries(store, FakeReports()).for_run(SOURCE_FGR_RUN, "otra", 7) == []


async def test_manda_con_el_pdf_y_queda_enviado(tmp_path: Path) -> None:
    pdf = tmp_path / "fgr.pdf"
    pdf.write_bytes(b"%PDF")
    store = await store_with_rule(())
    await PlanDeliveries(store, FakeReports(pdf=pdf)).for_run(SOURCE_FGR_RUN, "corrida-1", 7)
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
    store = await store_with_rule(())
    await PlanDeliveries(store, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", 7)
    use, _ = sender_for(store, SendResult(False, error="Composio: timeout", retryable=True))

    await use.send_due()

    [delivery] = store.deliveries.values()
    assert delivery.status is DeliveryStatus.PENDING
    assert delivery.last_error == "Composio: timeout"
    assert delivery.next_attempt_at is not None and delivery.next_attempt_at > NOW

    store2 = await store_with_rule(())
    await PlanDeliveries(store2, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", 7)
    use2, _ = sender_for(store2, SendResult(False, error="401 unauthorized", retryable=False))
    await use2.send_due()
    [failed] = store2.deliveries.values()
    assert (failed.status, failed.next_attempt_at) == (DeliveryStatus.FAILED, None)


async def test_sin_llave_o_sin_cuenta_activa_falla_sin_intentar_el_proveedor() -> None:
    store = await store_with_rule(())
    await PlanDeliveries(store, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", 7)
    fake = FakeSender(configured=False)
    use = SendDeliveries(store, FakeReports(), {DeliveryChannel.EMAIL: fake}, now=lambda: NOW)

    await use.send_due()

    [delivery] = store.deliveries.values()
    assert delivery.status is DeliveryStatus.FAILED
    assert "COMPOSIO_API_KEY" in (delivery.last_error or "")
    assert fake.sent == []


async def test_mandar_prueba_y_reintentar() -> None:
    store = await store_with_rule(())
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
    store = await store_with_rule(())
    use, _ = sender_for(store)

    with pytest.raises(DeliveryNotFoundError, match="corrida"):
        await SendTest(store, FakeReports(ref=None), use).execute(SOURCE_FGR_RUN, 1, 1)
    with pytest.raises(DeliveryNotFoundError):
        await SendTest(store, FakeReports(), use).execute(SOURCE_FGR_RUN, 99, 1)


async def test_reglas_invalidas() -> None:
    store = await store_with_rule(())
    await ManageRecipients(store).create("Solo WhatsApp", None, "525512345678")
    rules = ManageRules(store)

    with pytest.raises(DeliveryValidationError, match="no tiene correo"):
        await rules.create(RuleDraft(SOURCE_FGR_RUN, 2, DeliveryChannel.EMAIL, 1, ()))
    with pytest.raises(DeliveryValidationError, match="cuenta de correo"):
        await rules.create(RuleDraft(SOURCE_FGR_RUN, 1, DeliveryChannel.EMAIL, None, ()))
    with pytest.raises(DeliveryValidationError, match="fuente"):
        await rules.create(RuleDraft("otra.cosa", 1, DeliveryChannel.EMAIL, 1, ()))
    with pytest.raises(DeliveryValidationError, match="WhatsApp"):
        await rules.create(RuleDraft(SOURCE_FGR_RUN, 1, DeliveryChannel.WHATSAPP, None, ()))
    with pytest.raises(DeliveryNotFoundError):
        await rules.update(99, RuleDraft(SOURCE_FGR_RUN, 1, DeliveryChannel.EMAIL, 1, ()))
    edited = await rules.update(
        1, RuleDraft(SOURCE_FGR_RUN, 1, DeliveryChannel.EMAIL, 1, (23, 7), False)
    )
    assert (edited.data.hours, edited.data.is_active) == ((7, 23), False)


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
