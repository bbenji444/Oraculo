"""Puertos de los envíos (F12.11, ADR-0039).

- ``DeliveryStorePort``: cuentas, destinatarios, reglas y la guía de cada envío.
- ``DeliverySenderPort``: manda un mensaje por un canal (correo vía Composio;
  WhatsApp más adelante).
- ``AccountConnectorPort``: conecta una cuenta de correo nueva y revisa su estado.
- ``ReportSourcePort``: lo que se manda de una corrida (resumen y PDF).

No hace: ninguna regla de negocio (eso es ``app.domain.deliveries``).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.application.pagination import TimeCursor
from app.domain.deliveries import (
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
    DeliveryStatus,
    RecipientDraft,
)


@dataclass(frozen=True, slots=True)
class DeliveryAccount:
    """Una cuenta desde la que se manda."""

    id: int
    provider: AccountProvider
    label: str
    address: str | None
    external_id: str | None
    status: AccountStatus


@dataclass(frozen=True, slots=True)
class Recipient:
    """Un destinatario guardado.

    Attributes:
        id: Id.
        data: Sus datos.
        owner: De quién es (``username``, ADR-0045).
    """

    id: int
    data: RecipientDraft
    owner: str = ""


@dataclass(frozen=True, slots=True)
class RuleDraft:
    """Cómo se manda lo de una fuente: por qué canal, desde qué cuenta y si está prendido.

    Hay una sola por fuente y canal. Se manda a **todos** los destinatarios
    activos en cada corrida del horario único (ADR-0040): no hay horas ni
    destinatarios por regla.

    Attributes:
        source: Fuente («monitor.corrida_fgr»).
        channel: Canal.
        account_id: Cuenta desde la que se manda (correo).
        is_active: Si manda.
    """

    source: str
    channel: DeliveryChannel
    account_id: int | None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class DeliveryRule:
    """Una regla guardada."""

    id: int
    data: RuleDraft


@dataclass(frozen=True, slots=True)
class NewDelivery:
    """Una guía por crear."""

    id: UUID
    rule_id: int | None
    source: str
    source_ref: str
    channel: DeliveryChannel
    account_id: int | None
    recipient_id: int | None
    destination: str
    subject: str
    attachment_name: str | None
    idempotency_key: str
    is_test: bool = False
    scheduled_for: datetime | None = None
    # De quién es el envío (el dueño del destinatario); ``None`` = el dueño
    # del destinatario lo pone la base.
    owner: str | None = None


@dataclass(frozen=True, slots=True)
class Delivery:
    """Una guía de envío con su estado."""

    id: UUID
    rule_id: int | None
    source: str
    source_ref: str
    channel: DeliveryChannel
    account_id: int | None
    recipient_id: int | None
    recipient_name: str | None
    destination: str
    subject: str
    attachment_name: str | None
    status: DeliveryStatus
    attempts: int
    last_error: str | None
    provider_ref: str | None
    is_test: bool
    created_at: datetime
    sent_at: datetime | None
    next_attempt_at: datetime | None
    scheduled_for: datetime | None = None
    owner: str = ""


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Lo que pasó en un intento."""

    delivery_id: UUID
    attempt: int
    ok: bool
    provider_status: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class SendResult:
    """Respuesta del proveedor a un envío.

    Attributes:
        ok: Si el proveedor lo aceptó.
        provider_status: Lo que respondió, en corto (por ejemplo, ``202``).
        provider_ref: Número del mensaje, si lo da.
        error: Explicación en español, si falló.
        retryable: Si vale la pena reintentar (caída o límite, no un correo inválido).
    """

    ok: bool
    provider_status: str | None = None
    provider_ref: str | None = None
    error: str | None = None
    retryable: bool = True


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    """Lo que se manda."""

    destination: str
    destination_name: str | None
    subject: str
    html_body: str
    attachment: Path | None = None


@dataclass(frozen=True, slots=True)
class ConnectionStart:
    """Una conexión de cuenta iniciada: falta que alguien abra el link y autorice."""

    external_id: str
    connect_url: str


@dataclass(frozen=True, slots=True)
class RemoteAccount:
    """Estado de una cuenta conectada según el proveedor."""

    status: AccountStatus
    address: str | None


@dataclass(frozen=True, slots=True)
class ReportContent:
    """Lo que se manda de una corrida."""

    source_ref: str
    title: str
    subject: str
    html_body: str
    pdf_path: Path | None
    slot_hour: int | None = None
    highlights: tuple[str, ...] = field(default_factory=tuple)


class DeliveryStorePort(Protocol):
    """Cuentas, destinatarios, reglas y guías de envío."""

    async def list_accounts(self) -> list[DeliveryAccount]:
        """Todas las cuentas de envío."""
        ...

    async def get_account(self, account_id: int) -> DeliveryAccount | None:
        """Una cuenta por id."""
        ...

    async def save_account(
        self,
        provider: AccountProvider,
        label: str,
        external_id: str | None,
        status: AccountStatus,
        address: str | None = None,
    ) -> DeliveryAccount:
        """Guarda una cuenta nueva (o la actualiza si ya existe ese ``external_id``)."""
        ...

    async def update_account(
        self, account_id: int, status: AccountStatus, address: str | None
    ) -> DeliveryAccount:
        """Cambia el estado y la dirección de una cuenta."""
        ...

    async def list_recipients(self) -> list[Recipient]:
        """Los destinatarios que ve quien pregunta, en orden alfabético.

        En la API la seguridad por filas deja ver a cada persona solo los
        suyos; el superusuario y el worker ven todos (ADR-0045).
        """
        ...

    async def get_recipient(self, recipient_id: int) -> Recipient | None:
        """Un destinatario por id."""
        ...

    async def create_recipient(self, data: RecipientDraft, owner: str) -> Recipient:
        """Guarda un destinatario a nombre de ``owner``."""
        ...

    async def update_recipient(self, recipient_id: int, data: RecipientDraft) -> Recipient:
        """Reemplaza los datos de un destinatario (su dueño no cambia)."""
        ...

    async def delete_recipient(self, recipient_id: int) -> bool:
        """Borra un destinatario (sus envíos pasados quedan, sin su nombre)."""
        ...

    async def list_rules(
        self, source: str | None = None, active_only: bool = False
    ) -> list[DeliveryRule]:
        """Las reglas, opcionalmente de una fuente y solo las prendidas."""
        ...

    async def save_rule(self, data: RuleDraft) -> DeliveryRule:
        """Guarda la regla de su fuente y canal (la crea o la reemplaza)."""
        ...

    async def create_deliveries(self, deliveries: Sequence[NewDelivery]) -> list[UUID]:
        """Crea las guías que no existan (por ``idempotency_key``).

        Returns:
            Los ids de las guías creadas; las repetidas se omiten.
        """
        ...

    async def get_delivery(self, delivery_id: UUID) -> Delivery | None:
        """Una guía por id."""
        ...

    async def due_deliveries(self, now: datetime, limit: int) -> list[Delivery]:
        """Guías pendientes cuyo intento ya toca, las más viejas primero."""
        ...

    async def stuck_deliveries(self, claimed_before: datetime) -> list[Delivery]:
        """Guías que siguen «enviando» desde antes de ``claimed_before``.

        Pasa cuando el servidor se reinicia mientras un correo sale: nadie
        termina ese envío y la guía se queda así para siempre.
        """
        ...

    async def claim(self, delivery_id: UUID) -> bool:
        """Marca una guía como «enviando» si seguía pendiente (evita mandarla dos veces)."""
        ...

    async def record_attempt(
        self,
        attempt: AttemptRecord,
        status: DeliveryStatus,
        next_attempt_at: datetime | None,
        provider_ref: str | None,
    ) -> None:
        """Guarda el intento y el nuevo estado de la guía."""
        ...

    async def reset_for_retry(self, delivery_id: UUID, now: datetime) -> bool:
        """Vuelve a poner en pendiente una guía fallida (botón Reintentar)."""
        ...

    async def history(self, after: TimeCursor | None, limit: int) -> list[Delivery]:
        """Las guías, de la más nueva a la más vieja (paginación por cursor)."""
        ...

    async def attempts_of(self, delivery_id: UUID) -> list[AttemptRecord]:
        """Los intentos de una guía, en orden."""
        ...


class DeliverySenderPort(Protocol):
    """Manda un mensaje por un canal."""

    def is_configured(self) -> bool:
        """Si el canal tiene lo necesario (por ejemplo, la llave de Composio)."""
        ...

    async def send(self, account: DeliveryAccount, message: OutgoingMessage) -> SendResult:
        """Manda un mensaje desde esa cuenta.

        Nunca lanza por errores del proveedor: los devuelve en ``SendResult``.
        """
        ...


class AccountConnectorPort(Protocol):
    """Conecta cuentas de correo nuevas y revisa su estado."""

    def is_configured(self) -> bool:
        """Si hay llave para hablar con el proveedor."""
        ...

    async def start(self, provider: AccountProvider, label: str) -> ConnectionStart:
        """Inicia la conexión: devuelve el link para autorizar."""
        ...

    async def check(self, provider: AccountProvider, external_id: str) -> RemoteAccount:
        """Estado actual de la cuenta y su dirección de correo, si ya está activa."""
        ...


class ReportSourcePort(Protocol):
    """Lo que se manda de una corrida."""

    async def content_for(self, source: str, source_ref: str) -> ReportContent | None:
        """Resumen y PDF de esa corrida, o ``None`` si no existe."""
        ...

    async def latest_ref(self, source: str) -> str | None:
        """La corrida más reciente de esa fuente (para «Mandar prueba»)."""
        ...
