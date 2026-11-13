"""Casos de uso de los envíos (F12.11, ADR-0039).

- ``ManageRecipients``: los correos de cada persona (ADR-0045); un usuario
  normal tiene hasta dos.
- ``ManageRules`` y ``ManageAccounts``: lo que solo el superusuario maneja:
  desde qué cuenta se manda y si los envíos están prendidos.
- ``PlanDeliveries``: al terminar cada corrida, crea una guía por cada
  correo de los envíos programados que la reciben (ADR-0046).
- ``SendDeliveries``: manda las guías pendientes, con reintentos (1, 5 y 30
  minutos) y un registro por intento.
- ``SendTest``: «Mandar prueba»: la última corrida a un destinatario, ya.
- ``RetryDelivery``: el botón «Reintentar».

No hace: no sabe de Composio, Outlook ni del monitor; usa los puertos.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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
    INTERRUPTED_ERROR,
    SOURCES,
    STUCK_SENDING_MINUTES,
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
    DeliveryStatus,
    RecipientDraft,
    idempotency_key,
    next_attempt_at,
)
from app.domain.errors import (
    DeliveryChannelUnavailableError,
    DeliveryNotFoundError,
    DeliveryValidationError,
)

logger = logging.getLogger(__name__)

# Guías que se mandan por pasada: una corrida con muchos destinatarios se
# reparte en varias pasadas del reloj (cada minuto).
SEND_BATCH = 50


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _invalid(field: str, message: str) -> DeliveryValidationError:
    return DeliveryValidationError(message, {"problemas": [{"campo": field, "mensaje": message}]})


@dataclass(frozen=True, slots=True)
class RecipientScope:
    """Quién da de alta o edita destinatarios y qué se le permite (ADR-0045).

    Attributes:
        owner: A nombre de quién quedan los nuevos (``username``).
        limit: Cuántos puede tener; ``None`` = sin tope (superusuario).
    """

    owner: str
    limit: int | None = None


class ManageRecipients:
    """Alta y edición de destinatarios: los correos de cada persona."""

    def __init__(self, store: DeliveryStorePort) -> None:
        """Recibe el almacén de envíos.

        Args:
            store: Cuentas, destinatarios, reglas y guías.
        """
        self._store = store

    async def create(self, data: RecipientDraft, scope: RecipientScope) -> Recipient:
        """Da de alta un destinatario a nombre de quien lo pide.

        Args:
            data: Datos ya validados (``RecipientDraft.validated``).
            scope: Dueño y tope de destinatarios.

        Raises:
            DeliveryValidationError: Si pasa del tope.
        """
        if scope.limit is not None:
            own = [r for r in await self._store.list_recipients() if r.owner == scope.owner]
            if len(own) >= scope.limit:
                raise _invalid("email", f"Puedes tener hasta {scope.limit} correos.")
        return await self._store.create_recipient(data, scope.owner)

    async def update(
        self, recipient_id: int, data: RecipientDraft, scope: RecipientScope
    ) -> Recipient:
        """Reemplaza los datos de un destinatario; su dueño no cambia.

        Raises:
            DeliveryNotFoundError: Si no existe o no es de quien lo pide (la
                seguridad por filas no se lo deja ver).
        """
        if await self._store.get_recipient(recipient_id) is None:
            raise DeliveryNotFoundError("No existe ese destinatario.", {"id": recipient_id})
        return await self._store.update_recipient(recipient_id, data)

    async def delete(self, recipient_id: int) -> None:
        """Borra un destinatario; sus envíos pasados siguen en el historial.

        Raises:
            DeliveryNotFoundError: Si no existe.
        """
        if not await self._store.delete_recipient(recipient_id):
            raise DeliveryNotFoundError("No existe ese destinatario.", {"id": recipient_id})


class ManageRules:
    """Cómo se manda cada fuente: por qué canal, desde qué cuenta y si está prendido."""

    def __init__(self, store: DeliveryStorePort) -> None:
        """Recibe el almacén de envíos."""
        self._store = store

    async def save(self, data: RuleDraft) -> DeliveryRule:
        """Guarda cómo se manda una fuente: canal, cuenta y si está prendido.

        Hay una regla por fuente y canal; guardar otra la reemplaza.

        Raises:
            DeliveryValidationError: Fuente desconocida, WhatsApp (todavía no)
                o sin una cuenta de correo.
        """
        if data.source not in SOURCES:
            raise _invalid("source", "Esa fuente no existe.")
        if data.channel is DeliveryChannel.WHATSAPP:
            raise _invalid("channel", "WhatsApp llegará en una siguiente etapa.")
        account = await self._store.get_account(data.account_id) if data.account_id else None
        if account is None or account.provider.channel is not DeliveryChannel.EMAIL:
            raise _invalid("account_id", "Elige la cuenta de correo desde la que se manda.")
        return await self._store.save_rule(data)


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
    """Crea las guías de una corrida: su reporte a los correos que la reciben."""

    def __init__(self, store: DeliveryStorePort, reports: ReportSourcePort) -> None:
        """Recibe el almacén y la fuente de reportes."""
        self._store = store
        self._reports = reports

    async def for_run(
        self,
        source: str,
        source_ref: str,
        slot: datetime,
        recipients: Sequence[Recipient],
    ) -> list[UUID]:
        """Al terminar una corrida: manda su reporte por cada regla prendida.

        Args:
            source: Fuente («monitor.corrida_fgr»).
            source_ref: La corrida (id de la búsqueda).
            slot: Hora programada de la corrida.
            recipients: A quién: los correos de los envíos programados que
                pidieron esta corrida (``recipients_of``, ADR-0046).

        Returns:
            Las guías creadas (las que ya existían no se repiten).
        """
        content = await self._reports.content_for(source, source_ref)
        if content is None:
            return []
        active = [r for r in recipients if r.data.is_active]
        planned = [
            _new_delivery(
                _Target(rule.data.channel, recipient, rule.id, rule.data.account_id),
                content,
                source,
                scheduled_for=slot,
            )
            for rule in await self._store.list_rules(source, active_only=True)
            for recipient in active
        ]
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
    scheduled_for: datetime | None = None,
) -> NewDelivery:
    data = target.recipient.data
    destination = (data.email if target.channel is DeliveryChannel.EMAIL else data.phone) or ""
    key = idempotency_key(source, content.source_ref, target.channel, destination)
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
        owner=target.recipient.owner or None,
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
        """Manda las guías cuyo turno ya llegó.

        Antes, regresa a la fila las que se quedaron «enviando» porque el
        servidor se reinició a media entrega (``release_stuck``).
        """
        sent = failed = 0
        await self.release_stuck()
        due = await self._store.due_deliveries(self._now(), limit)
        for delivery in due:
            status = await self.send_one(delivery)
            sent += status is DeliveryStatus.SENT
            failed += status in (DeliveryStatus.FAILED, DeliveryStatus.SKIPPED)
        return SendReport(len(due), sent, failed)

    async def release_stuck(self) -> int:
        """Reintenta las guías que se cortaron a medias.

        Una guía «enviando» por más de ``STUCK_SENDING_MINUTES`` se cortó (el
        12/11/2026 la VM se reinició a las 07:04 y el correo de Geovanni se
        quedó así). Cuenta como un intento fallido, con su razón en el
        historial, y vuelve a la fila para salir en esta misma pasada. Si ya
        no le quedan intentos, se da por fallida: una guía que siempre tumba
        el envío no se reintenta para siempre.

        Si el correo sí alcanzó a salir antes del corte, llegará dos veces:
        es preferible a que no llegue.

        Returns:
            Cuántas guías se liberaron.
        """
        now = self._now()
        stuck = await self._store.stuck_deliveries(now - timedelta(minutes=STUCK_SENDING_MINUTES))
        for delivery in stuck:
            attempt = delivery.attempts + 1
            # El corte no fue culpa del proveedor: no hay que esperar, solo
            # saber si quedan intentos.
            retry = next_attempt_at(attempt, now) is not None
            await self._store.record_attempt(
                AttemptRecord(delivery.id, attempt, False, None, INTERRUPTED_ERROR, now, now),
                DeliveryStatus.PENDING if retry else DeliveryStatus.FAILED,
                now if retry else None,
                None,
            )
            logger.warning(
                "Envío cortado a medias: vuelve a la fila",
                extra={"delivery_id": str(delivery.id), "attempt": attempt, "retry": retry},
            )
        return len(stuck)

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

    async def execute(
        self, source: str, recipient_id: int, account_id: int | None = None
    ) -> Delivery:
        """Crea una guía de prueba y la manda ya.

        Args:
            source: Fuente («monitor.corrida_fgr»).
            recipient_id: A quién.
            account_id: Desde qué cuenta; sin ella, la de la regla de correo
                de la fuente (la que eligió el superusuario, ADR-0045).

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
        if account_id is None:
            account_id = await sender_account_id(self._store, source)
        if account_id is None or await self._store.get_account(account_id) is None:
            raise DeliveryNotFoundError(
                "Todavía no hay una cuenta que envíe; pídesela al administrador.",
                {"id": account_id},
            )
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


async def sender_account_id(store: DeliveryStorePort, source: str) -> int | None:
    """La cuenta de correo desde la que se manda una fuente.

    Es la de su regla de correo; si hay varias, la prendida primero.

    Returns:
        El id de la cuenta, o ``None`` si nadie la ha elegido.
    """
    rules = [
        r
        for r in await store.list_rules(source)
        if r.data.channel is DeliveryChannel.EMAIL and r.data.account_id is not None
    ]
    rules.sort(key=lambda r: (not r.data.is_active, r.id))
    return rules[0].data.account_id if rules else None


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
