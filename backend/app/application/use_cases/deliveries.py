"""Casos de uso de los envíos (F12.11, ADR-0039).

- ``ManageRecipients``, ``ManageRules`` y ``ManageAccounts``: lo que Benji
  administra en la pantalla «Envíos».
- ``PlanDeliveries``: crea una guía por destinatario de cada regla que manda
  en ese momento. Al terminar una corrida (``for_run``) se manda el reporte
  recién hecho; a una hora programada sin corrida (``scheduled``), el más
  reciente.
- ``SendDeliveries``: manda las guías pendientes, con reintentos (1, 5 y 30
  minutos) y un registro por intento.
- ``SendTest``: «Mandar prueba»: la última corrida a un destinatario, ya.
- ``RetryDelivery``: el botón «Reintentar».

No hace: no sabe de Composio, Outlook ni del monitor; usa los puertos.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.application.ports.deliveries import (
    AccountConnectorPort,
    AttemptRecord,
    Delivery,
    DeliveryAccount,
    DeliveryRule,
    DeliverySenderPort,
    DeliveryStorePort,
    NewDelivery,
    OutgoingMessage,
    Recipient,
    ReportContent,
    ReportSourcePort,
    RuleDraft,
)
from app.domain.deliveries import (
    MINUTES_PER_HOUR,
    SOURCES,
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
    DeliveryStatus,
    RecipientDraft,
    RuleAudience,
    format_time,
    idempotency_key,
    next_attempt_at,
    rule_due,
    rule_targets,
    validate_days,
    validate_times,
)
from app.domain.errors import (
    DeliveryChannelUnavailableError,
    DeliveryNotFoundError,
    DeliveryValidationError,
)

# Guías que se mandan por pasada: una corrida con muchos destinatarios se
# reparte en varias pasadas del reloj (cada minuto).
SEND_BATCH = 50
MEXICO_CITY = ZoneInfo("America/Mexico_City")
MAX_RULE_NAME = 80


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _invalid(field: str, message: str) -> DeliveryValidationError:
    return DeliveryValidationError(message, {"problemas": [{"campo": field, "mensaje": message}]})


class ManageRecipients:
    """Alta y edición de destinatarios."""

    def __init__(self, store: DeliveryStorePort) -> None:
        """Recibe el almacén de envíos.

        Args:
            store: Cuentas, destinatarios, reglas y guías.
        """
        self._store = store

    async def create(
        self, name: str, email: str | None, phone: str | None, is_active: bool = True
    ) -> Recipient:
        """Da de alta un destinatario.

        Raises:
            DeliveryValidationError: Si los datos no son válidos.
        """
        return await self._store.create_recipient(
            RecipientDraft.validated(name, email, phone, is_active)
        )

    async def update(
        self, recipient_id: int, name: str, email: str | None, phone: str | None, is_active: bool
    ) -> Recipient:
        """Reemplaza los datos de un destinatario.

        Raises:
            DeliveryNotFoundError: Si no existe.
            DeliveryValidationError: Si los datos no son válidos.
        """
        if await self._store.get_recipient(recipient_id) is None:
            raise DeliveryNotFoundError("No existe ese destinatario.", {"id": recipient_id})
        return await self._store.update_recipient(
            recipient_id, RecipientDraft.validated(name, email, phone, is_active)
        )

    async def delete(self, recipient_id: int) -> None:
        """Borra un destinatario; sus envíos pasados siguen en el historial.

        Raises:
            DeliveryNotFoundError: Si no existe.
        """
        if not await self._store.delete_recipient(recipient_id):
            raise DeliveryNotFoundError("No existe ese destinatario.", {"id": recipient_id})


class ManageRules:
    """Alta y edición de reglas: qué, a quién, por dónde, desde qué cuenta y cuándo."""

    def __init__(self, store: DeliveryStorePort) -> None:
        """Recibe el almacén de envíos."""
        self._store = store

    async def _validated(self, data: RuleDraft) -> RuleDraft:
        if data.source not in SOURCES:
            raise _invalid("source", "Esa fuente no existe.")
        name = " ".join(data.name.split())
        if not name:
            raise _invalid("name", "Ponle un nombre a la regla.")
        if len(name) > MAX_RULE_NAME:
            raise _invalid("name", f"Máximo {MAX_RULE_NAME} caracteres.")
        known = {r.id for r in await self._store.list_recipients()}
        chosen = tuple(dict.fromkeys(i for i in data.recipient_ids if i in known))
        excluded = tuple(dict.fromkeys(i for i in data.exclude_ids if i in known))
        if data.audience is RuleAudience.SELECTED and not chosen:
            raise _invalid("recipient_ids", "Elige al menos un destinatario.")
        if data.channel is DeliveryChannel.WHATSAPP:
            raise _invalid("channel", "WhatsApp llegará en una siguiente etapa.")
        account = await self._store.get_account(data.account_id) if data.account_id else None
        if account is None or account.provider.channel is not DeliveryChannel.EMAIL:
            raise _invalid("account_id", "Elige la cuenta de correo desde la que se manda.")
        return RuleDraft(
            source=data.source,
            name=name,
            audience=data.audience,
            recipient_ids=chosen if data.audience is RuleAudience.SELECTED else (),
            exclude_ids=excluded if data.audience is RuleAudience.ALL else (),
            channel=data.channel,
            account_id=data.account_id,
            times=validate_times(data.times),
            days=validate_days(data.days),
            is_active=data.is_active,
        )

    async def create(self, data: RuleDraft) -> DeliveryRule:
        """Guarda una regla nueva.

        Raises:
            DeliveryValidationError: Si la regla no tiene sentido (sin correo,
                sin cuenta, fuente desconocida u horas inválidas).
        """
        return await self._store.create_rule(await self._validated(data))

    async def update(self, rule_id: int, data: RuleDraft) -> DeliveryRule:
        """Reemplaza una regla.

        Raises:
            DeliveryNotFoundError: Si no existe.
            DeliveryValidationError: Ver ``create``.
        """
        if await self._store.get_rule(rule_id) is None:
            raise DeliveryNotFoundError("No existe esa regla.", {"id": rule_id})
        return await self._store.update_rule(rule_id, await self._validated(data))

    async def delete(self, rule_id: int) -> None:
        """Borra una regla; sus envíos pasados siguen en el historial.

        Raises:
            DeliveryNotFoundError: Si no existe.
        """
        if not await self._store.delete_rule(rule_id):
            raise DeliveryNotFoundError("No existe esa regla.", {"id": rule_id})


class ManageAccounts:
    """Conectar cuentas de correo y revisar su estado."""

    def __init__(self, store: DeliveryStorePort, connector: AccountConnectorPort) -> None:
        """Recibe el almacén y el conector de cuentas (Composio)."""
        self._store = store
        self._connector = connector

    async def connect(self, provider: AccountProvider, label: str) -> tuple[DeliveryAccount, str]:
        """Inicia la conexión de una cuenta de correo.

        Returns:
            La cuenta guardada como pendiente y el link que hay que abrir.

        Raises:
            DeliveryChannelUnavailableError: WhatsApp todavía no, o falta la
                llave de Composio.
            DeliveryValidationError: Sin nombre para la cuenta.
        """
        if provider is AccountProvider.WHATSAPP:
            raise DeliveryChannelUnavailableError("WhatsApp llegará en una siguiente etapa.")
        if not self._connector.is_configured():
            raise DeliveryChannelUnavailableError(
                "Falta COMPOSIO_API_KEY en el .env para conectar cuentas."
            )
        clean = " ".join(label.split())
        if not clean:
            raise _invalid("label", "Ponle un nombre a la cuenta.")
        started = await self._connector.start(provider, clean)
        account = await self._store.save_account(
            provider, clean, started.external_id, AccountStatus.PENDING
        )
        return account, started.connect_url

    async def refresh(self, account_id: int) -> DeliveryAccount:
        """Revisa con el proveedor si la cuenta ya quedó autorizada.

        Raises:
            DeliveryNotFoundError: Si no existe.
            DeliveryChannelUnavailableError: Sin llave de Composio.
        """
        account = await self._store.get_account(account_id)
        if account is None:
            raise DeliveryNotFoundError("No existe esa cuenta de envío.", {"id": account_id})
        if account.external_id is None or account.provider is AccountProvider.WHATSAPP:
            return account
        if not self._connector.is_configured():
            raise DeliveryChannelUnavailableError("Falta COMPOSIO_API_KEY en el .env.")
        remote = await self._connector.check(account.provider, account.external_id)
        return await self._store.update_account(
            account.id, remote.status, remote.address or account.address
        )


class PlanDeliveries:
    """Crea las guías que tocan: al terminar una corrida o a una hora programada."""

    def __init__(self, store: DeliveryStorePort, reports: ReportSourcePort) -> None:
        """Recibe el almacén y la fuente de reportes."""
        self._store = store
        self._reports = reports

    async def for_run(self, source: str, source_ref: str, slot: datetime) -> list[UUID]:
        """Al terminar una corrida: manda su reporte a las reglas de esa hora.

        Args:
            source: Fuente («monitor.corrida_fgr»).
            source_ref: La corrida (id de la búsqueda).
            slot: Hora programada de la corrida.

        Returns:
            Las guías creadas (las que ya existían no se repiten).
        """
        content = await self._reports.content_for(source, source_ref)
        if content is None:
            return []
        return await self._plan(source, content, slot.astimezone(MEXICO_CITY), slot_key=None)

    async def scheduled(
        self, source: str, now: datetime, run_minutes: frozenset[int]
    ) -> list[UUID]:
        """A una hora programada sin corrida: manda el reporte más reciente.

        Las horas que coinciden con una corrida las atiende ``for_run``, cuando
        el reporte ya está hecho; aquí se saltan.

        Args:
            source: Fuente.
            now: Este minuto.
            run_minutes: Minutos del día con corrida (07:00 = 420, …).

        Returns:
            Las guías creadas.
        """
        local = now.astimezone(MEXICO_CITY).replace(second=0, microsecond=0)
        minute = local.hour * MINUTES_PER_HOUR + local.minute
        if minute in run_minutes:
            return []
        ref = await self._reports.latest_ref(source)
        content = await self._reports.content_for(source, ref) if ref else None
        if content is None:
            return []
        slot_key = f"{local:%Y-%m-%d} {format_time(minute)}"
        return await self._plan(source, content, local, slot_key=slot_key)

    async def _plan(
        self, source: str, content: ReportContent, local: datetime, slot_key: str | None
    ) -> list[UUID]:
        active = [(r.id, r) for r in await self._store.list_recipients() if r.data.is_active]
        planned: list[NewDelivery] = []
        for rule in await self._store.list_rules(source, active_only=True):
            data = rule.data
            if not rule_due(data.times, data.days, local):
                continue
            for recipient in rule_targets(
                data.audience, data.recipient_ids, data.exclude_ids, active
            ):
                target = _Target(data.channel, recipient, rule.id, data.account_id)
                planned.append(_new_delivery(target, content, source, slot=(slot_key, local)))
        return await self._store.create_deliveries([p for p in planned if p.destination])


@dataclass(frozen=True, slots=True)
class _Target:
    """A quién y por dónde va una guía."""

    channel: DeliveryChannel
    recipient: Recipient
    rule_id: int | None
    account_id: int | None


def _new_delivery(
    target: _Target,
    content: ReportContent,
    source: str,
    *,
    is_test: bool = False,
    slot: tuple[str | None, datetime | None] = (None, None),
) -> NewDelivery:
    data = target.recipient.data
    destination = (data.email if target.channel is DeliveryChannel.EMAIL else data.phone) or ""
    slot_key, scheduled_for = slot
    key = idempotency_key(source, content.source_ref, target.channel, destination, slot_key)
    return NewDelivery(
        id=uuid4(),
        rule_id=target.rule_id,
        source=source,
        source_ref=content.source_ref,
        channel=target.channel,
        account_id=target.account_id,
        recipient_id=target.recipient.id,
        destination=destination,
        subject=content.subject,
        attachment_name=content.pdf_path.name if content.pdf_path else None,
        # Las pruebas se pueden repetir: su llave lleva su propio id.
        idempotency_key=f"test|{uuid4()}|{key}" if is_test else key,
        is_test=is_test,
        scheduled_for=scheduled_for,
    )


@dataclass(frozen=True, slots=True)
class SendReport:
    """Resultado de una pasada de envíos."""

    attempted: int
    sent: int
    failed: int


class SendDeliveries:
    """Manda guías pendientes y registra cada intento."""

    def __init__(
        self,
        store: DeliveryStorePort,
        reports: ReportSourcePort,
        senders: Mapping[DeliveryChannel, DeliverySenderPort],
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        """Recibe el almacén, la fuente de reportes y un emisor por canal."""
        self._store = store
        self._reports = reports
        self._senders = senders
        self._now = now

    async def send_due(self, limit: int = SEND_BATCH) -> SendReport:
        """Manda las guías cuyo turno ya llegó."""
        sent = failed = 0
        due = await self._store.due_deliveries(self._now(), limit)
        for delivery in due:
            status = await self.send_one(delivery)
            sent += status is DeliveryStatus.SENT
            failed += status in (DeliveryStatus.FAILED, DeliveryStatus.SKIPPED)
        return SendReport(len(due), sent, failed)

    async def send_one(self, delivery: Delivery) -> DeliveryStatus:
        """Intenta mandar una guía y deja el intento registrado.

        Returns:
            El estado en que quedó la guía.
        """
        if not await self._store.claim(delivery.id):
            return delivery.status  # otra pasada ya la tomó
        started = self._now()
        attempt = delivery.attempts + 1
        ok, provider_status, provider_ref, error, retryable = await self._try(delivery)
        finished = self._now()
        if ok:
            status, retry_at = DeliveryStatus.SENT, None
        else:
            retry_at = next_attempt_at(attempt, finished) if retryable else None
            status = DeliveryStatus.PENDING if retry_at else DeliveryStatus.FAILED
        await self._store.record_attempt(
            AttemptRecord(delivery.id, attempt, ok, provider_status, error, started, finished),
            status,
            retry_at,
            provider_ref,
        )
        return status

    async def _try(
        self, delivery: Delivery
    ) -> tuple[bool, str | None, str | None, str | None, bool]:
        sender = self._senders.get(delivery.channel)
        if sender is None or not sender.is_configured():
            reason = (
                "WhatsApp todavía no está disponible."
                if delivery.channel is DeliveryChannel.WHATSAPP
                else "Falta COMPOSIO_API_KEY en el .env."
            )
            return False, None, None, reason, False
        account = (
            await self._store.get_account(delivery.account_id) if delivery.account_id else None
        )
        if account is None or account.status is not AccountStatus.ACTIVE:
            return False, None, None, "La cuenta de envío no existe o no está activa.", False
        content = await self._reports.content_for(delivery.source, delivery.source_ref)
        if content is None:
            return False, None, None, "Ya no existe el reporte de esa corrida.", False
        message = OutgoingMessage(
            destination=delivery.destination,
            destination_name=delivery.recipient_name,
            subject=delivery.subject,
            html_body=content.html_body,
            attachment=content.pdf_path,
        )
        result = await sender.send(account, message)
        return (
            result.ok,
            result.provider_status,
            result.provider_ref,
            result.error,
            result.retryable,
        )


class SendTest:
    """«Mandar prueba»: la última corrida a un destinatario, en este momento."""

    def __init__(
        self, store: DeliveryStorePort, reports: ReportSourcePort, sender: SendDeliveries
    ) -> None:
        """Recibe el almacén, la fuente de reportes y quien manda."""
        self._store = store
        self._reports = reports
        self._sender = sender

    async def execute(self, source: str, recipient_id: int, account_id: int) -> Delivery:
        """Crea una guía de prueba y la manda ya.

        Returns:
            La guía con el resultado del intento.

        Raises:
            DeliveryNotFoundError: Si no hay destinatario, cuenta o corrida.
            DeliveryValidationError: Si el destinatario no tiene correo.
        """
        recipient = await self._store.get_recipient(recipient_id)
        if recipient is None:
            raise DeliveryNotFoundError("No existe ese destinatario.", {"id": recipient_id})
        if not recipient.data.email:
            raise _invalid("recipient_id", "Ese destinatario no tiene correo.")
        if await self._store.get_account(account_id) is None:
            raise DeliveryNotFoundError("No existe esa cuenta de envío.", {"id": account_id})
        ref = await self._reports.latest_ref(source)
        content = await self._reports.content_for(source, ref) if ref else None
        if content is None:
            raise DeliveryNotFoundError("Todavía no hay una corrida con reporte para mandar.")
        target = _Target(DeliveryChannel.EMAIL, recipient, None, account_id)
        new = _new_delivery(target, content, source, is_test=True)
        [created] = await self._store.create_deliveries([new])
        delivery = await self._store.get_delivery(created)
        if delivery is None:  # se acaba de crear en la misma llamada
            raise DeliveryNotFoundError("No se pudo crear la prueba.")
        await self._sender.send_one(delivery)
        final = await self._store.get_delivery(created)
        return final or delivery


class RetryDelivery:
    """El botón «Reintentar» de una guía que falló."""

    def __init__(self, store: DeliveryStorePort, sender: SendDeliveries) -> None:
        """Recibe el almacén y quien manda."""
        self._store = store
        self._sender = sender

    async def execute(self, delivery_id: UUID) -> Delivery:
        """Vuelve a intentar una guía fallida, sin borrar sus intentos anteriores.

        Raises:
            DeliveryNotFoundError: Si no existe.
            DeliveryValidationError: Si no está fallida.
        """
        delivery = await self._store.get_delivery(delivery_id)
        if delivery is None:
            raise DeliveryNotFoundError("No existe ese envío.", {"id": str(delivery_id)})
        if delivery.status not in (DeliveryStatus.FAILED, DeliveryStatus.SKIPPED):
            raise _invalid("status", "Solo se reintenta un envío que falló.")
        await self._store.reset_for_retry(delivery_id, _utc_now())
        pending = await self._store.get_delivery(delivery_id)
        if pending is not None:
            await self._sender.send_one(pending)
        return await self._store.get_delivery(delivery_id) or delivery
