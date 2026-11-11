"""Casos de uso de los envíos (ADR-0039, ADR-0045), con piezas en memoria."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.application.ports.deliveries import Recipient, RemoteAccount, RuleDraft, SendResult
from app.application.use_cases.deliveries import (
    ManageAccounts,
    ManageRecipients,
    ManageRules,
    PlanDeliveries,
    RecipientScope,
    RetryDelivery,
    SendDeliveries,
    SendTest,
    sender_account_id,
)
from app.domain.deliveries import (
    MAX_RECIPIENTS_PER_USER,
    SOURCE_FGR_RUN,
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
    DeliveryStatus,
    RecipientDraft,
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
AT_1500 = datetime(2026, 11, 6, 21, 0, tzinfo=UTC)
BENJI = RecipientScope("benji")


async def add(
    store: FakeDeliveryStore,
    name: str,
    email: str | None,
    *,
    phone: str | None = None,
    is_active: bool = True,
    scope: RecipientScope = BENJI,
) -> Recipient:
    data = RecipientDraft.validated(name, email, phone, is_active)
    return await ManageRecipients(store).create(data, scope)


def draft(
    *,
    channel: DeliveryChannel = DeliveryChannel.EMAIL,
    account_id: int | None = 1,
    source: str = SOURCE_FGR_RUN,
    is_active: bool = True,
) -> RuleDraft:
    return RuleDraft(source=source, channel=channel, account_id=account_id, is_active=is_active)


async def store_with_rule(rule: RuleDraft | None = None) -> FakeDeliveryStore:
    store = FakeDeliveryStore()
    await store.save_account(AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.ACTIVE)
    await add(store, "Benjamin", "benji@hotmail.com")
    await ManageRules(store).save(rule or draft())
    return store


def sender_for(
    store: FakeDeliveryStore, *results: SendResult, pdf: Path | None = None
) -> tuple[SendDeliveries, FakeSender]:
    fake = FakeSender(*results)
    use = SendDeliveries(
        store, FakeReports(pdf=pdf), {DeliveryChannel.EMAIL: fake}, now=lambda: NOW
    )
    return use, fake


async def test_cada_corrida_manda_su_reporte_una_sola_vez() -> None:
    store = await store_with_rule()
    plan = PlanDeliveries(store, FakeReports())

    first = await plan.for_run(SOURCE_FGR_RUN, "corrida-1", AT_1500, await store.list_recipients())
    again = await plan.for_run(SOURCE_FGR_RUN, "corrida-1", AT_1500, await store.list_recipients())

    assert (len(first), again) == (1, [])
    [delivery] = store.deliveries.values()
    assert (delivery.destination, delivery.subject, delivery.scheduled_for) == (
        "benji@hotmail.com",
        "Reporte FGR · corrida 06/11/2026, 15:00 (CDMX)",
        AT_1500,
    )


async def test_la_corrida_va_a_todos_los_activos_con_correo() -> None:
    # Benji, 06/11/2026: un solo reporte para todos (ADR-0040).
    store = await store_with_rule()
    await add(store, "Geovanni", "geo@x.mx")
    await add(store, "Tadeo", "tadeo@x.mx", is_active=False)
    await add(store, "Solo WhatsApp", None, phone="525512345678")

    await PlanDeliveries(store, FakeReports()).for_run(
        SOURCE_FGR_RUN, "corrida-1", AT_1500, await store.list_recipients()
    )

    assert sorted(d.destination for d in store.deliveries.values()) == [
        "benji@hotmail.com",
        "geo@x.mx",
    ]


async def test_con_la_regla_apagada_no_se_manda_nada() -> None:
    store = await store_with_rule(draft(is_active=False))

    assert (
        await PlanDeliveries(store, FakeReports()).for_run(
            SOURCE_FGR_RUN, "corrida-1", AT_1500, await store.list_recipients()
        )
        == []
    )


async def test_destinatario_apagado_o_corrida_inexistente_no_crean_guias() -> None:
    store = await store_with_rule()
    off = RecipientDraft.validated("Benjamin", "benji@hotmail.com", None, False)
    await ManageRecipients(store).update(1, off, BENJI)
    plan = PlanDeliveries(store, FakeReports())

    assert (
        await plan.for_run(SOURCE_FGR_RUN, "corrida-1", AT_0700, await store.list_recipients())
        == []
    )
    assert await plan.for_run(SOURCE_FGR_RUN, "otra", AT_0700, await store.list_recipients()) == []


async def test_manda_con_el_pdf_y_queda_enviado(tmp_path: Path) -> None:
    pdf = tmp_path / "fgr.pdf"
    pdf.write_bytes(b"%PDF")
    store = await store_with_rule()
    await PlanDeliveries(store, FakeReports(pdf=pdf)).for_run(
        SOURCE_FGR_RUN, "corrida-1", AT_0700, await store.list_recipients()
    )
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
    await PlanDeliveries(store, FakeReports()).for_run(
        SOURCE_FGR_RUN, "corrida-1", AT_0700, await store.list_recipients()
    )
    use, _ = sender_for(store, SendResult(False, error="Composio: timeout", retryable=True))

    await use.send_due()

    [delivery] = store.deliveries.values()
    assert delivery.status is DeliveryStatus.PENDING
    assert delivery.last_error == "Composio: timeout"
    assert delivery.next_attempt_at is not None and delivery.next_attempt_at > NOW

    store2 = await store_with_rule()
    await PlanDeliveries(store2, FakeReports()).for_run(
        SOURCE_FGR_RUN, "corrida-1", AT_0700, await store2.list_recipients()
    )
    use2, _ = sender_for(store2, SendResult(False, error="401 unauthorized", retryable=False))
    await use2.send_due()
    [failed] = store2.deliveries.values()
    assert (failed.status, failed.next_attempt_at) == (DeliveryStatus.FAILED, None)


async def test_sin_llave_o_sin_cuenta_activa_falla_sin_intentar_el_proveedor() -> None:
    store = await store_with_rule()
    await PlanDeliveries(store, FakeReports()).for_run(
        SOURCE_FGR_RUN, "corrida-1", AT_0700, await store.list_recipients()
    )
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
    rules = ManageRules(await store_with_rule())

    with pytest.raises(DeliveryValidationError, match="cuenta de correo"):
        await rules.save(draft(account_id=None))
    with pytest.raises(DeliveryValidationError, match="cuenta de correo"):
        await rules.save(draft(account_id=99))
    with pytest.raises(DeliveryValidationError, match="fuente"):
        await rules.save(draft(source="otra.cosa"))
    with pytest.raises(DeliveryValidationError, match="WhatsApp"):
        await rules.save(draft(channel=DeliveryChannel.WHATSAPP))


async def test_guardar_otra_vez_reemplaza_la_regla_de_la_fuente() -> None:
    store = await store_with_rule()

    saved = await ManageRules(store).save(draft(is_active=False))

    assert (saved.id, saved.data.is_active) == (1, False)
    assert len(await store.list_rules(SOURCE_FGR_RUN)) == 1


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
        await ManageRecipients(FakeDeliveryStore()).update(
            1, RecipientDraft.validated("Ana", "ana@x.mx", None), BENJI
        )


# --- Envíos por usuario (ADR-0045) y programados (ADR-0046) ---


async def test_la_corrida_va_solo_a_los_correos_que_la_pidieron() -> None:
    store = await store_with_rule()
    ana = await add(store, "Ana", "ana@x.mx", scope=RecipientScope("ana"))

    await PlanDeliveries(store, FakeReports()).for_run(SOURCE_FGR_RUN, "corrida-1", AT_0700, [ana])

    assert [d.destination for d in store.deliveries.values()] == ["ana@x.mx"]


async def test_cada_envio_queda_a_nombre_del_dueno_del_correo() -> None:
    store = await store_with_rule()
    await add(store, "Ana", "ana@x.mx", scope=RecipientScope("ana"))

    await PlanDeliveries(store, FakeReports()).for_run(
        SOURCE_FGR_RUN, "corrida-1", AT_0700, await store.list_recipients()
    )

    owners = {d.destination: d.owner for d in store.deliveries.values()}
    assert owners == {"benji@hotmail.com": "benji", "ana@x.mx": "ana"}


async def test_un_usuario_tiene_hasta_dos_correos_y_el_superusuario_sin_tope() -> None:
    store = FakeDeliveryStore()
    ana = RecipientScope("ana", limit=MAX_RECIPIENTS_PER_USER)
    await add(store, "Ana", "ana@x.mx", scope=ana)
    await add(store, "Ana trabajo", "ana@fgr.mx", scope=ana)
    # Los de otra persona no cuentan para su tope.
    await add(store, "Benjamin", "benji@hotmail.com")

    with pytest.raises(DeliveryValidationError, match="hasta 2 correos"):
        await add(store, "Ana otro", "ana2@x.mx", scope=ana)
    for n in range(3):
        await add(store, f"Lista {n}", f"lista{n}@x.mx")
    assert len(await store.list_recipients()) == 6


async def test_la_prueba_sale_de_la_cuenta_que_eligio_el_superusuario() -> None:
    store = await store_with_rule()
    use, fake = sender_for(store, SendResult(True, "202"))

    sent = await SendTest(store, FakeReports(), use).execute(SOURCE_FGR_RUN, 1)

    assert (sent.status, sent.account_id) == (DeliveryStatus.SENT, 1)
    assert len(fake.sent) == 1


async def test_sin_cuenta_elegida_la_prueba_lo_dice() -> None:
    store = FakeDeliveryStore()
    await add(store, "Ana", "ana@x.mx")
    use, _ = sender_for(store)

    assert await sender_account_id(store, SOURCE_FGR_RUN) is None
    with pytest.raises(DeliveryNotFoundError, match="administrador"):
        await SendTest(store, FakeReports(), use).execute(SOURCE_FGR_RUN, 1)
