"""Adaptador de Composio con un cliente falso: nunca llama a internet ni manda nada."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.delivery.composio_channels import (
    ComposioAccountConnector,
    ComposioClient,
    ComposioEmailSender,
    WhatsAppSender,
)
from app.application.ports.deliveries import DeliveryAccount, OutgoingMessage
from app.domain.deliveries import AccountProvider, AccountStatus

pytestmark = pytest.mark.anyio

OVITECH = DeliveryAccount(1, AccountProvider.OUTLOOK, "Ovitech", None, "ca_1", AccountStatus.ACTIVE)
MESSAGE = OutgoingMessage("benji@hotmail.com", "Benjamin", "Reporte FGR", "<p>Hola</p>")


class FakeTools:
    def __init__(self, reply: dict[str, Any] | Exception) -> None:
        self.reply = reply
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def execute(self, slug: str, arguments: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self.calls.append((slug, arguments, kwargs))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FakeAccounts:
    def __init__(self) -> None:
        self.linked: dict[str, Any] = {}

    def link(self, **kwargs: Any) -> dict[str, str]:
        self.linked = kwargs
        return {"id": "ca_nueva", "redirect_url": "https://connect.composio.dev/link/lk_1"}

    def get(self, external_id: str) -> SimpleNamespace:
        return SimpleNamespace(status="ACTIVE", id=external_id)


class FakeConfigs:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.created: list[str] = []

    def list(self) -> SimpleNamespace:
        return SimpleNamespace(items=self.items)

    def create(self, toolkit: str, options: dict[str, str]) -> dict[str, str]:
        self.created.append(toolkit)
        return {"id": f"ac_{toolkit}"}


def client(tools: FakeTools, configs: FakeConfigs | None = None) -> ComposioClient:
    # Imita el cliente real de Composio: solo los atributos que usa el adaptador.
    fake: ComposioClient = SimpleNamespace(
        tools=tools, connected_accounts=FakeAccounts(), auth_configs=configs or FakeConfigs([])
    )
    return fake


async def test_manda_por_outlook_con_adjunto_y_la_cuenta_correcta(tmp_path: Path) -> None:
    pdf = tmp_path / "fgr.pdf"
    tools = FakeTools({"successful": True, "data": {"status_code": 202}, "error": None})
    sender = ComposioEmailSender(lambda: client(tools), "oraculo-monitor")

    result = await sender.send(OVITECH, replace(MESSAGE, attachment=pdf))

    assert (result.ok, result.provider_status) == (True, "202")
    slug, arguments, kwargs = tools.calls[0]
    assert slug == "OUTLOOK_SEND_EMAIL"
    assert (arguments["to"], arguments["is_html"], arguments["attachment"]) == (
        "benji@hotmail.com",
        True,
        str(pdf),
    )
    assert (kwargs["user_id"], kwargs["connected_account_id"]) == ("oraculo-monitor", "ca_1")


async def test_gmail_usa_su_herramienta_y_su_campo() -> None:
    tools = FakeTools({"successful": True, "data": {"id": "m1"}, "error": None})
    gmail = DeliveryAccount(2, AccountProvider.GMAIL, "Gmail", None, "ca_2", AccountStatus.ACTIVE)

    result = await ComposioEmailSender(lambda: client(tools), "u").send(gmail, MESSAGE)

    assert (result.ok, result.provider_ref) == (True, "m1")
    assert tools.calls[0][0] == "GMAIL_SEND_EMAIL"
    assert tools.calls[0][1]["recipient_email"] == "benji@hotmail.com"


async def test_errores_pasajeros_y_permanentes() -> None:
    down = await ComposioEmailSender(lambda: client(FakeTools(TimeoutError("timeout"))), "u").send(
        OVITECH, MESSAGE
    )
    denied = await ComposioEmailSender(
        lambda: client(FakeTools({"successful": False, "data": {}, "error": "403 Forbidden"})), "u"
    ).send(OVITECH, MESSAGE)
    no_key = await ComposioEmailSender(None, "u").send(OVITECH, MESSAGE)

    assert (down.ok, down.retryable) == (False, True)
    assert (denied.ok, denied.retryable, denied.error) == (False, False, "403 Forbidden")
    assert (no_key.ok, no_key.retryable) == (False, False)
    assert not ComposioEmailSender(None, "u").is_configured()


async def test_conectar_crea_la_configuracion_si_falta_y_da_el_link() -> None:
    configs = FakeConfigs([])
    fake = client(FakeTools({}), configs)
    connector = ComposioAccountConnector(lambda: fake, "oraculo-monitor")

    started = await connector.start(AccountProvider.OUTLOOK, "Ovitech")

    assert (started.external_id, started.connect_url) == (
        "ca_nueva",
        "https://connect.composio.dev/link/lk_1",
    )
    assert configs.created == ["outlook"]
    assert fake.connected_accounts.linked["auth_config_id"] == "ac_outlook"


async def test_conectar_reutiliza_la_configuracion_y_revisa_la_direccion() -> None:
    configs = FakeConfigs([{"id": "ac_x", "toolkit": {"slug": "outlook"}}])
    tools = FakeTools({"successful": True, "data": {"mail": "ovitech_22@hotmail.com"}})
    connector = ComposioAccountConnector(lambda: client(tools, configs), "u")

    await connector.start(AccountProvider.OUTLOOK, "Ovitech")
    remote = await connector.check(AccountProvider.OUTLOOK, "ca_1")

    assert configs.created == []
    assert (remote.status, remote.address) == (AccountStatus.ACTIVE, "ovitech_22@hotmail.com")


async def test_whatsapp_todavia_no() -> None:
    whatsapp = WhatsAppSender()

    assert not whatsapp.is_configured()
    assert not (await whatsapp.send(OVITECH, MESSAGE)).ok
