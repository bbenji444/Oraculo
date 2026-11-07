"""Correo por Composio, y el lugar reservado para WhatsApp (F12.11, ADR-0039).

Composio es el «llavero» que guarda la autorización de cada cuenta de correo
(Outlook u Gmail) y manda en su nombre. Aquí viven:

- ``ComposioEmailSender``: manda un correo con el PDF adjunto desde una cuenta
  conectada (``DeliverySenderPort``);
- ``ComposioAccountConnector``: crea el link para conectar una cuenta nueva y
  revisa si ya quedó autorizada (``AccountConnectorPort``);
- ``WhatsAppSender``: el botón existe, el canal todavía no.

La librería ``composio`` es síncrona: se llama en otro hilo. Solo puede subir
archivos de la carpeta de reportes (``file_upload_dirs``): si por un error se
le pidiera adjuntar el ``.env``, se niega.

Comprobado contra la librería 0.31 el 07/11/2026: ``tools.execute`` con
``connected_account_id``, ``connected_accounts.link`` (el método anterior,
``initiate``, ya no sirve para cuentas administradas por Composio) y
``auth_configs.create`` con ``use_composio_managed_auth``.

No hace: no decide reintentos ni guarda nada (eso es del caso de uso).
"""

import asyncio
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from composio import Composio

from app.application.ports.deliveries import (
    ConnectionStart,
    DeliveryAccount,
    OutgoingMessage,
    RemoteAccount,
    SendResult,
)
from app.domain.deliveries import AccountProvider, AccountStatus

logger = logging.getLogger(__name__)

# Herramienta de Composio que manda el correo, y cómo se llama su campo de destino.
_SEND_TOOL: Mapping[AccountProvider, tuple[str, str]] = {
    AccountProvider.OUTLOOK: ("OUTLOOK_SEND_EMAIL", "to"),
    AccountProvider.GMAIL: ("GMAIL_SEND_EMAIL", "recipient_email"),
}
# Herramienta que dice la dirección de la cuenta conectada.
# VERIFICAR: el campo de Gmail (emailAddress) solo se probó en la documentación.
_PROFILE_TOOL: Mapping[AccountProvider, str] = {
    AccountProvider.OUTLOOK: "OUTLOOK_GET_PROFILE",
    AccountProvider.GMAIL: "GMAIL_GET_PROFILE",
}
_ACCOUNT_STATUS: Mapping[str, AccountStatus] = {
    "ACTIVE": AccountStatus.ACTIVE,
    "INITIATED": AccountStatus.PENDING,
    "INITIALIZING": AccountStatus.PENDING,
    "FAILED": AccountStatus.FAILED,
    "EXPIRED": AccountStatus.FAILED,
    "INACTIVE": AccountStatus.DISABLED,
    "REVOKED": AccountStatus.DISABLED,
}
# Palabras de un error que no se arregla reintentando (permiso, destino inválido).
_PERMANENT_HINTS = ("401", "403", "invalid", "not found", "permission", "unauthorized")


class ComposioClient(Protocol):
    """Lo que se usa de ``composio.Composio`` (permite probar sin internet)."""

    @property
    def tools(self) -> Any:
        """Ejecución de herramientas."""
        ...

    @property
    def connected_accounts(self) -> Any:
        """Cuentas conectadas."""
        ...

    @property
    def auth_configs(self) -> Any:
        """Configuraciones de autenticación."""
        ...


def build_composio_client(api_key: str, upload_dir: Path) -> ComposioClient:
    """Crea el cliente real de Composio, con el candado de carpeta.

    Args:
        api_key: Llave del proyecto (ak_).
        upload_dir: Única carpeta de la que puede subir archivos.

    Returns:
        El cliente.
    """
    client: ComposioClient = Composio(
        api_key=api_key,
        dangerously_allow_auto_upload_download_files=True,
        file_upload_dirs=[str(upload_dir)],
        sensitive_file_upload_protection=True,
    )
    return client


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    return dump() if callable(dump) else dict(vars(value))


def _retryable(error: str) -> bool:
    lowered = error.lower()
    return not any(hint in lowered for hint in _PERMANENT_HINTS)


class ComposioEmailSender:
    """Manda correos desde una cuenta conectada en Composio."""

    def __init__(self, client_factory: Callable[[], ComposioClient] | None, user_id: str) -> None:
        """Recibe cómo crear el cliente (``None`` = sin llave) y el dueño de las cuentas.

        Args:
            client_factory: Crea el cliente de Composio; ``None`` si no hay llave.
            user_id: Usuario de Composio dueño de las cuentas («oraculo-monitor»).
        """
        self._factory = client_factory
        self._user_id = user_id

    def is_configured(self) -> bool:
        """Ver ``DeliverySenderPort.is_configured``."""
        return self._factory is not None

    async def send(self, account: DeliveryAccount, message: OutgoingMessage) -> SendResult:
        """Ver ``DeliverySenderPort.send``."""
        if self._factory is None or account.external_id is None:
            return SendResult(
                False, error="Falta la llave de Composio o la cuenta.", retryable=False
            )
        tool = _SEND_TOOL.get(account.provider)
        if tool is None:
            return SendResult(False, error="Esa cuenta no manda correo.", retryable=False)
        slug, to_field = tool
        arguments: dict[str, Any] = {
            to_field: message.destination,
            "subject": message.subject,
            "body": message.html_body,
            "is_html": True,
        }
        if message.attachment is not None:
            arguments["attachment"] = str(message.attachment)
        factory = self._factory
        try:
            raw = await asyncio.to_thread(
                lambda: factory().tools.execute(
                    slug,
                    arguments,
                    user_id=self._user_id,
                    connected_account_id=account.external_id,
                    dangerously_skip_version_check=True,
                )
            )
        except Exception as error:
            # La librería lanza por red, llave o archivo: queda en el intento.
            logger.warning("Composio no aceptó el envío", extra={"error": str(error)})
            return SendResult(False, error=f"Composio: {error}", retryable=_retryable(str(error)))
        result = _as_dict(raw)
        data = _as_dict(result.get("data") or {})
        status = str(data.get("status_code") or data.get("status") or "")
        if result.get("successful"):
            ref = data.get("id") or data.get("message_id") or data.get("internetMessageId")
            return SendResult(
                True, provider_status=status or "ok", provider_ref=str(ref) if ref else None
            )
        error_text = str(result.get("error") or "El proveedor rechazó el envío.")
        return SendResult(
            False,
            provider_status=status or None,
            error=error_text,
            retryable=_retryable(error_text),
        )


class ComposioAccountConnector:
    """Conecta cuentas de correo en el proyecto de Composio."""

    def __init__(self, client_factory: Callable[[], ComposioClient] | None, user_id: str) -> None:
        """Recibe cómo crear el cliente y el dueño de las cuentas."""
        self._factory = client_factory
        self._user_id = user_id

    def is_configured(self) -> bool:
        """Ver ``AccountConnectorPort.is_configured``."""
        return self._factory is not None

    def _client(self) -> ComposioClient:
        if self._factory is None:
            raise RuntimeError("Falta COMPOSIO_API_KEY")
        return self._factory()

    def _auth_config_id(self, client: ComposioClient, provider: AccountProvider) -> str:
        configs = getattr(client.auth_configs.list(), "items", [])
        for config in configs:
            data = _as_dict(config)
            if (_as_dict(data.get("toolkit") or {})).get("slug") == provider.value:
                return str(data["id"])
        created = _as_dict(
            client.auth_configs.create(
                toolkit=provider.value, options={"type": "use_composio_managed_auth"}
            )
        )
        return str(created["id"])

    async def start(self, provider: AccountProvider, label: str) -> ConnectionStart:
        """Ver ``AccountConnectorPort.start``."""

        def run() -> ConnectionStart:
            client = self._client()
            config_id = self._auth_config_id(client, provider)
            request = _as_dict(
                client.connected_accounts.link(
                    user_id=self._user_id, auth_config_id=config_id, allow_multiple=True
                )
            )
            return ConnectionStart(str(request["id"]), str(request["redirect_url"]))

        return await asyncio.to_thread(run)

    async def check(self, provider: AccountProvider, external_id: str) -> RemoteAccount:
        """Ver ``AccountConnectorPort.check``."""

        def run() -> RemoteAccount:
            client = self._client()
            account = _as_dict(client.connected_accounts.get(external_id))
            status = _ACCOUNT_STATUS.get(str(account.get("status")), AccountStatus.PENDING)
            address = None
            if status is AccountStatus.ACTIVE:
                address = self._address(client, provider, external_id)
            return RemoteAccount(status, address)

        return await asyncio.to_thread(run)

    def _address(
        self, client: ComposioClient, provider: AccountProvider, external_id: str
    ) -> str | None:
        try:
            result = _as_dict(
                client.tools.execute(
                    _PROFILE_TOOL[provider],
                    {},
                    user_id=self._user_id,
                    connected_account_id=external_id,
                    dangerously_skip_version_check=True,
                )
            )
        except Exception:
            logger.warning("No se pudo leer la dirección de la cuenta", exc_info=True)
            return None
        data = _as_dict(result.get("data") or {})
        profile = _as_dict(data.get("response_data") or data)
        address = (
            profile.get("mail") or profile.get("userPrincipalName") or profile.get("emailAddress")
        )
        return str(address) if address else None


class WhatsAppSender:
    """WhatsApp: el botón existe en pantalla; el envío llega en otra etapa."""

    def is_configured(self) -> bool:
        """Ver ``DeliverySenderPort.is_configured``: todavía no."""
        return False

    async def send(self, account: DeliveryAccount, message: OutgoingMessage) -> SendResult:
        """Ver ``DeliverySenderPort.send``."""
        return SendResult(False, error="WhatsApp todavía no está disponible.", retryable=False)
