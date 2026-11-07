"""Envíos desde el worker (F12.11, ADR-0039).

- ``deliver_run``: al terminar una corrida automática, crea las guías de las
  reglas que le tocan a esa hora y las manda. Solo si ``DELIVERIES_ENABLED``.
- ``send_due_deliveries``: lo lanza el reloj cada minuto; manda lo pendiente,
  incluidos los reintentos.

Un fallo aquí nunca tumba la corrida: la búsqueda y su PDF ya quedaron
guardados, y cada envío fallido queda en su guía.

No hace: no decide reglas (eso es ``app.application.use_cases.deliveries``).
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.delivery.factory import build_sender
from app.adapters.persistence.deliveries_repository import PostgresDeliveryStore
from app.adapters.persistence.delivery_reports import PostgresRunReports
from app.application.use_cases.deliveries import PlanDeliveries, SendReport
from app.core.config import Settings
from app.domain.deliveries import SOURCE_FGR_RUN

logger = logging.getLogger(__name__)


async def deliver_run(settings: Settings, search_id: UUID, slot_hour: int) -> SendReport | None:
    """Crea y manda los envíos de una corrida.

    Args:
        settings: Configuración.
        search_id: La corrida.
        slot_hour: Su hora en la CDMX (7, 15 o 23).

    Returns:
        Cuántos se intentaron y mandaron, o ``None`` si los envíos están apagados.
    """
    if not settings.deliveries_enabled:
        return None
    engine = create_async_engine(settings.database_url())
    try:
        created = await PlanDeliveries(
            PostgresDeliveryStore(engine), PostgresRunReports(engine)
        ).for_run(SOURCE_FGR_RUN, str(search_id), slot_hour)
        report = await build_sender(settings, engine).send_due()
        logger.info(
            "Envíos de la corrida",
            extra={
                "search_id": str(search_id),
                "created": len(created),
                "sent": report.sent,
                "failed": report.failed,
            },
        )
        return report
    except Exception:
        logger.exception("Fallaron los envíos de la corrida", extra={"search_id": str(search_id)})
        return None
    finally:
        await engine.dispose()


async def send_due_deliveries(settings: Settings) -> SendReport:
    """Manda las guías pendientes cuyo turno ya llegó (reintentos incluidos).

    Args:
        settings: Configuración.

    Returns:
        Cuántas se intentaron, mandaron y fallaron.
    """
    engine = create_async_engine(settings.database_url())
    try:
        return await build_sender(settings, engine).send_due()
    finally:
        await engine.dispose()
