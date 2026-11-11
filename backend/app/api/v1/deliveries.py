"""Pantalla «Envíos» (``/deliveries``, F12.11, ADR-0039).

Qué se manda, a quién y por qué canal. Cada persona da de alta sus correos
(hasta dos, ADR-0045) y arma sus envíos programados: qué temas, de dónde, a
qué horas y qué días (``/deliveries/schedules``, ADR-0046). El correo que
envía lo decide el superusuario.

- ``GET /deliveries/overview``: si están prendidos, si Composio está listo
  y cuántos correos puede tener la persona (desde qué correo se manda, solo
  al superusuario);
- ``/deliveries/accounts``: cuentas de envío (conectar Outlook o Gmail y
  revisar si ya quedaron autorizadas; WhatsApp «próximamente»). Superusuario;
- ``/deliveries/recipients``: los destinatarios de la persona (el
  superusuario ve todos, con su dueño);
- ``/deliveries/rules``: por qué canal y desde qué cuenta se manda cada
  fuente. Superusuario;
- ``/deliveries/history``: la guía de cada envío de la persona, con sus
  intentos y «Reintentar»;
- ``POST /deliveries/test``: «Mandar prueba» con la última corrida.

Quién ve qué lo decide la seguridad por filas de la base (migración 0042):
aquí solo se dice a nombre de quién se crea cada destinatario.

No hace: ninguna regla de negocio; traduce entre HTTP y los casos de uso.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, status
from pydantic import BaseModel, Field

from app.api.auth import CurrentUser, SuperUser
from app.api.errors import ERROR_RESPONSES, error_responses
from app.application.pagination import TimeCursor, decode_time_cursor, encode_time_cursor
from app.application.ports.deliveries import (
    AccountConnectorPort,
    AttemptRecord,
    Delivery,
    DeliveryAccount,
    DeliveryRule,
    DeliveryStorePort,
    Recipient,
    ReportSourcePort,
    RuleDraft,
)
from app.application.use_cases.deliveries import (
    ManageAccounts,
    ManageRecipients,
    ManageRules,
    RecipientScope,
    RetryDelivery,
    SendDeliveries,
    SendTest,
    sender_account_id,
)
from app.domain.access import AuthUser
from app.domain.deliveries import (
    MAX_RECIPIENTS_PER_USER,
    SOURCE_FGR_RUN,
    SOURCES,
    AccountProvider,
    DeliveryChannel,
    RecipientDraft,
    mask_destination,
)
from app.domain.errors import DeliveryNotFoundError

router = APIRouter(prefix="/deliveries", tags=["envíos"], responses=ERROR_RESPONSES)

# Historial: lo que cabe en una pantalla sin desplazarse demasiado.
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200


def get_delivery_store(request: Request) -> DeliveryStorePort:
    """Almacén de envíos creado al arrancar."""
    store: DeliveryStorePort = request.app.state.delivery_store
    return store


def get_delivery_connector(request: Request) -> AccountConnectorPort:
    """Conector de cuentas de correo (Composio)."""
    connector: AccountConnectorPort = request.app.state.delivery_connector
    return connector


def get_delivery_sender(request: Request) -> SendDeliveries:
    """Caso de uso que manda las guías."""
    sender: SendDeliveries = request.app.state.delivery_sender
    return sender


def get_delivery_reports(request: Request) -> ReportSourcePort:
    """Fuente de reportes de las corridas."""
    reports: ReportSourcePort = request.app.state.delivery_reports
    return reports


Store = Annotated[DeliveryStorePort, Depends(get_delivery_store)]
Connector = Annotated[AccountConnectorPort, Depends(get_delivery_connector)]
Sender = Annotated[SendDeliveries, Depends(get_delivery_sender)]
Reports = Annotated[ReportSourcePort, Depends(get_delivery_reports)]


# --- Esquemas ---


class SourceOut(BaseModel):
    """Una fuente de lo que se manda."""

    id: str = Field(examples=[SOURCE_FGR_RUN])
    label: str


class OverviewOut(BaseModel):
    """Estado general de los envíos."""

    enabled: bool = Field(description="Si las corridas automáticas mandan (DELIVERIES_ENABLED).")
    email_configured: bool = Field(description="Si hay llave de Composio para el correo.")
    whatsapp_available: bool = Field(description="WhatsApp: todavía no.")
    sources: list[SourceOut]
    sender_address: str | None = Field(
        default=None,
        description="Desde qué correo se manda (lo elige el superusuario).",
        examples=["ovitech_22@hotmail.com"],
    )
    max_recipients: int | None = Field(
        default=None, description="Cuántos correos puede tener la persona; null = sin tope."
    )


def get_delivery_settings(request: Request) -> OverviewOut:
    """Lo que se sabe de la configuración (sin secretos)."""
    overview: OverviewOut = request.app.state.delivery_overview
    return overview


Overview = Annotated[OverviewOut, Depends(get_delivery_settings)]


class AccountOut(BaseModel):
    """Una cuenta desde la que se manda."""

    id: int
    provider: AccountProvider
    channel: DeliveryChannel
    label: str
    address: str | None
    status: str

    @classmethod
    def of(cls, a: DeliveryAccount) -> "AccountOut":
        """Convierte del caso de uso."""
        return cls(
            id=a.id,
            provider=a.provider,
            channel=a.provider.channel,
            label=a.label,
            address=a.address,
            status=a.status.value,
        )


class AccountIn(BaseModel):
    """Cuenta por conectar."""

    provider: AccountProvider = Field(examples=["outlook"])
    label: str = Field(min_length=1, max_length=80, examples=["Reportes Oráculo"])


class ConnectOut(BaseModel):
    """Cuenta pendiente y el link para autorizarla."""

    account: AccountOut
    connect_url: str


class RecipientIn(BaseModel):
    """Datos de un destinatario."""

    name: str = Field(examples=["Benjamin Oviedo"])
    email: str | None = Field(default=None, examples=["benjamon_300@hotmail.com"])
    phone: str | None = Field(default=None, examples=["525512345678"])
    is_active: bool = True

    def draft(self) -> RecipientDraft:
        """Los datos validados para el caso de uso.

        Raises:
            DeliveryValidationError: Si los datos no son válidos.
        """
        return RecipientDraft.validated(self.name, self.email, self.phone, self.is_active)


class RecipientOut(RecipientIn):
    """Un destinatario guardado."""

    id: int
    owner: str = Field(description="De quién es (usuario).", examples=["benji"])

    @classmethod
    def of(cls, r: Recipient) -> "RecipientOut":
        """Convierte del caso de uso."""
        d = r.data
        return cls(
            id=r.id,
            name=d.name,
            email=d.email,
            phone=d.phone,
            is_active=d.is_active,
            owner=r.owner,
        )


class RuleIn(BaseModel):
    """Cómo se manda una fuente: canal, cuenta y si está prendida.

    Se manda a todos los destinatarios activos en cada corrida del horario
    único (``/schedule``).
    """

    source: str = Field(default=SOURCE_FGR_RUN, examples=[SOURCE_FGR_RUN])
    channel: DeliveryChannel = DeliveryChannel.EMAIL
    account_id: int | None = Field(default=None, examples=[1])
    is_active: bool = True

    def draft(self) -> RuleDraft:
        """La regla para el caso de uso."""
        return RuleDraft(
            source=self.source,
            channel=self.channel,
            account_id=self.account_id,
            is_active=self.is_active,
        )


class RuleOut(RuleIn):
    """La regla guardada."""

    id: int

    @classmethod
    def of(cls, rule: DeliveryRule) -> "RuleOut":
        """Convierte del caso de uso."""
        d = rule.data
        return cls(
            id=rule.id,
            source=d.source,
            channel=d.channel,
            account_id=d.account_id,
            is_active=d.is_active,
        )


class AttemptOut(BaseModel):
    """Un intento de un envío."""

    attempt: int
    ok: bool
    provider_status: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime

    @classmethod
    def of(cls, a: AttemptRecord) -> "AttemptOut":
        """Convierte del caso de uso."""
        return cls(
            attempt=a.attempt,
            ok=a.ok,
            provider_status=a.provider_status,
            error=a.error,
            started_at=a.started_at,
            finished_at=a.finished_at,
        )


class DeliveryOut(BaseModel):
    """La guía de un envío."""

    id: UUID
    source: str
    source_label: str
    source_ref: str
    rule_id: int | None
    channel: DeliveryChannel
    account_id: int | None
    recipient_id: int | None
    recipient_name: str | None
    destination: str = Field(description="Enmascarado (be•••@hotmail.com).")
    subject: str
    attachment_name: str | None
    status: str
    attempts: int
    last_error: str | None
    provider_ref: str | None
    is_test: bool
    created_at: datetime
    sent_at: datetime | None
    next_attempt_at: datetime | None
    scheduled_for: datetime | None = Field(
        default=None, description="Hora programada que lo mandó."
    )
    owner: str = Field(default="", description="De quién es el envío (usuario).")
    attempt_log: list[AttemptOut] = Field(default_factory=list)

    @classmethod
    def of(cls, d: Delivery, attempts: list[AttemptRecord] | None = None) -> "DeliveryOut":
        """Convierte del caso de uso."""
        return cls(
            id=d.id,
            source=d.source,
            source_label=SOURCES.get(d.source, d.source),
            source_ref=d.source_ref,
            rule_id=d.rule_id,
            channel=d.channel,
            account_id=d.account_id,
            recipient_id=d.recipient_id,
            recipient_name=d.recipient_name,
            destination=mask_destination(d.destination),
            subject=d.subject,
            attachment_name=d.attachment_name,
            status=d.status.value,
            attempts=d.attempts,
            last_error=d.last_error,
            provider_ref=d.provider_ref,
            is_test=d.is_test,
            created_at=d.created_at,
            sent_at=d.sent_at,
            next_attempt_at=d.next_attempt_at,
            scheduled_for=d.scheduled_for,
            owner=d.owner,
            attempt_log=[AttemptOut.of(a) for a in attempts or []],
        )


class HistoryOut(BaseModel):
    """Una página del historial."""

    items: list[DeliveryOut]
    next_cursor: str | None


class TestIn(BaseModel):
    """«Mandar prueba»."""

    source: Literal["monitor.corrida_fgr"] = "monitor.corrida_fgr"
    recipient_id: int
    account_id: int | None = Field(
        default=None,
        description=(
            "Desde qué cuenta (solo superusuario); sin ella, la que eligió el superusuario."
        ),
    )


DeliveryId = Annotated[UUID, Path(description="Id del envío.")]


def _scope(user: AuthUser) -> RecipientScope:
    """Dueño y tope de quien da de alta o edita."""
    return RecipientScope(
        owner=user.username, limit=None if user.is_superuser else MAX_RECIPIENTS_PER_USER
    )


# --- Rutas ---


@router.get("/overview", response_model=OverviewOut, summary="Estado de los envíos")
async def overview(
    settings: Overview, connector: Connector, store: Store, user: CurrentUser
) -> OverviewOut:
    """Si están prendidos, si el correo está listo y el tope de correos.

    Desde qué correo se manda solo se le dice al superusuario (Benji, 11/11/2026).
    """
    account_id = await sender_account_id(store, SOURCE_FGR_RUN) if user.is_superuser else None
    account = await store.get_account(account_id) if account_id else None
    return settings.model_copy(
        update={
            "email_configured": connector.is_configured(),
            "sender_address": account.address if account else None,
            "max_recipients": None if user.is_superuser else MAX_RECIPIENTS_PER_USER,
        }
    )


@router.get("/accounts", response_model=list[AccountOut], summary="Cuentas de envío")
async def list_accounts(_: SuperUser, store: Store) -> list[AccountOut]:
    """Las cuentas desde las que se manda."""
    return [AccountOut.of(a) for a in await store.list_accounts()]


@router.post(
    "/accounts",
    response_model=ConnectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Conectar una cuenta de correo",
    responses=error_responses(503),
)
async def connect_account(
    _: SuperUser, body: AccountIn, store: Store, connector: Connector
) -> ConnectOut:
    """Crea la cuenta como pendiente y devuelve el link para autorizarla."""
    account, url = await ManageAccounts(store, connector).connect(body.provider, body.label)
    return ConnectOut(account=AccountOut.of(account), connect_url=url)


@router.post(
    "/accounts/{account_id}/refresh",
    response_model=AccountOut,
    summary="Revisar si la cuenta ya quedó autorizada",
    responses=error_responses(404, 503),
)
async def refresh_account(
    _: SuperUser, account_id: int, store: Store, connector: Connector
) -> AccountOut:
    """Pregunta al proveedor el estado de la cuenta y su dirección."""
    return AccountOut.of(await ManageAccounts(store, connector).refresh(account_id))


@router.get("/recipients", response_model=list[RecipientOut], summary="Destinatarios")
async def list_recipients(store: Store) -> list[RecipientOut]:
    """Los destinatarios de la persona (el superusuario ve todos)."""
    return [RecipientOut.of(r) for r in await store.list_recipients()]


@router.post(
    "/recipients",
    response_model=RecipientOut,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar destinatario",
)
async def create_recipient(body: RecipientIn, store: Store, user: CurrentUser) -> RecipientOut:
    """Da de alta un destinatario a nombre de la persona (un usuario, hasta dos)."""
    created = await ManageRecipients(store).create(body.draft(), _scope(user))
    return RecipientOut.of(created)


@router.put(
    "/recipients/{recipient_id}",
    response_model=RecipientOut,
    summary="Editar destinatario",
    responses=error_responses(404),
)
async def update_recipient(
    recipient_id: int, body: RecipientIn, store: Store, user: CurrentUser
) -> RecipientOut:
    """Reemplaza los datos de un destinatario (también para desactivarlo)."""
    updated = await ManageRecipients(store).update(recipient_id, body.draft(), _scope(user))
    return RecipientOut.of(updated)


@router.delete(
    "/recipients/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar destinatario",
    responses=error_responses(404),
)
async def delete_recipient(recipient_id: int, store: Store) -> None:
    """Borra un destinatario; sus envíos pasados siguen en el historial."""
    await ManageRecipients(store).delete(recipient_id)


@router.get("/rules", response_model=list[RuleOut], summary="Cómo se manda cada fuente")
async def list_rules(_: SuperUser, store: Store) -> list[RuleOut]:
    """Las reglas: una por fuente y canal."""
    return [RuleOut.of(r) for r in await store.list_rules()]


@router.put("/rules", response_model=RuleOut, summary="Guardar cómo se manda")
async def save_rule(_: SuperUser, body: RuleIn, store: Store) -> RuleOut:
    """Guarda la regla de su fuente y canal (la crea o la reemplaza)."""
    return RuleOut.of(await ManageRules(store).save(body.draft()))


@router.get("/history", response_model=HistoryOut, summary="Historial de envíos")
async def history(
    store: Store,
    cursor: Annotated[str | None, Query(description="Cursor de la página anterior.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_HISTORY_LIMIT)] = DEFAULT_HISTORY_LIMIT,
) -> HistoryOut:
    """Las guías de envío de la persona, de la más nueva a la más vieja."""
    after = decode_time_cursor(cursor) if cursor else None
    rows = await store.history(after, limit + 1)
    page, more = rows[:limit], len(rows) > limit
    next_cursor = (
        encode_time_cursor(TimeCursor(page[-1].created_at, str(page[-1].id)))
        if more and page
        else None
    )
    return HistoryOut(items=[DeliveryOut.of(d) for d in page], next_cursor=next_cursor)


@router.get(
    "/history/{delivery_id}",
    response_model=DeliveryOut,
    summary="Detalle de un envío",
    responses=error_responses(404),
)
async def delivery_detail(delivery_id: DeliveryId, store: Store) -> DeliveryOut:
    """Un envío con todos sus intentos."""
    delivery = await store.get_delivery(delivery_id)
    if delivery is None:
        raise DeliveryNotFoundError("No existe ese envío.", {"id": str(delivery_id)})
    return DeliveryOut.of(delivery, await store.attempts_of(delivery_id))


@router.post(
    "/history/{delivery_id}/retry",
    response_model=DeliveryOut,
    summary="Reintentar un envío fallido",
    responses=error_responses(404),
)
async def retry(delivery_id: DeliveryId, store: Store, sender: Sender) -> DeliveryOut:
    """Vuelve a intentar sin borrar los intentos anteriores."""
    delivery = await RetryDelivery(store, sender).execute(delivery_id)
    return DeliveryOut.of(delivery, await store.attempts_of(delivery_id))


@router.post(
    "/test",
    response_model=DeliveryOut,
    summary="Mandar prueba",
    responses=error_responses(404),
)
async def send_test(
    body: TestIn, store: Store, reports: Reports, sender: Sender, user: CurrentUser
) -> DeliveryOut:
    """Manda ya la última corrida a un destinatario y devuelve cómo quedó.

    Un usuario normal no elige la cuenta: siempre sale del correo que eligió
    el superusuario.
    """
    account_id = body.account_id if user.is_superuser else None
    delivery = await SendTest(store, reports, sender).execute(
        body.source, body.recipient_id, account_id
    )
    return DeliveryOut.of(delivery, await store.attempts_of(delivery.id))
