"""Arma las piezas de los envíos desde la configuración (F12.11, ADR-0039).

Lo usan la API (pantalla «Envíos») y el worker (envíos al terminar cada
corrida y reintentos). Sin ``COMPOSIO_API_KEY`` todo se arma igual, pero el
correo queda «sin configurar» y los envíos fallan con un mensaje claro.

No hace: ninguna regla; solo conecta adaptadores con casos de uso.
"""

from collections.abc import Callable
from functools import cache

from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.delivery.composio_channels import (
    ComposioAccountConnector,
    ComposioClient,
    ComposioEmailSender,
    WhatsAppSender,
    build_composio_client,
)
from app.adapters.persistence.deliveries_repository import PostgresDeliveryStore
from app.adapters.persistence.delivery_reports import PostgresRunReports
from app.application.ports.deliveries import DeliverySenderPort
from app.application.use_cases.deliveries import SendDeliveries
from app.core.config import Settings
from app.domain.deliveries import DeliveryChannel


def composio_factory(settings: Settings) -> Callable[[], ComposioClient] | None:
    """Cómo crear el cliente de Composio, o ``None`` si no hay llave.

    El cliente se crea una vez y se reutiliza.
    """
    if settings.composio_api_key is None:
        return None
    api_key = settings.composio_api_key.get_secret_value()
    upload_dir = settings.reports_dir

    @cache
    def client() -> ComposioClient:
        return build_composio_client(api_key, upload_dir)

    return client


def build_senders(settings: Settings) -> dict[DeliveryChannel, DeliverySenderPort]:
    """Un emisor por canal."""
    return {
        DeliveryChannel.EMAIL: ComposioEmailSender(
            composio_factory(settings), settings.composio_user_id
        ),
        DeliveryChannel.WHATSAPP: WhatsAppSender(),
    }


def build_connector(settings: Settings) -> ComposioAccountConnector:
    """El conector de cuentas de correo."""
    return ComposioAccountConnector(composio_factory(settings), settings.composio_user_id)


def build_sender(settings: Settings, engine: AsyncEngine) -> SendDeliveries:
    """El caso de uso que manda guías, con sus piezas reales."""
    return SendDeliveries(
        PostgresDeliveryStore(engine), PostgresRunReports(engine), build_senders(settings)
    )
