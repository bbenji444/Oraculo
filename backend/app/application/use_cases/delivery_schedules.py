"""Casos de uso de los envíos programados (ADR-0046).

- ``ManageSchedules``: crear, editar y borrar los envíos de una persona, con
  sus reglas: temas y región que existan, correos que sean suyos y su tope de
  corridas al día.
- ``StarterSchedule``: el envío con que empieza cada usuario nuevo (la FGR a
  las 07:00, 15:00 y 23:00; Benji, 11/11/2026).
- ``PendingRuns``: lo que hace el reloj cada minuto: qué corridas tocan,
  agrupadas, ya apartadas para no lanzarlas dos veces.
- ``recipients_of``: a qué correos va una corrida.

No hace: no corre búsquedas ni manda correos (eso es el worker).
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.application.clock import MEXICO_CITY
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.deliveries import DeliveryStorePort, Recipient
from app.application.ports.delivery_schedules import (
    DeliverySchedule,
    DeliveryScheduleStorePort,
)
from app.application.ports.regions import RegionRepositoryPort
from app.application.use_cases.automatic_run import find_concept_id
from app.domain.delivery_schedules import (
    DueRun,
    ScheduledItem,
    ScheduleDraft,
    check_daily_limit,
    due_runs,
)
from app.domain.errors import DeliveryNotFoundError, DeliveryValidationError
from app.domain.schedule import RunSchedule

logger = logging.getLogger(__name__)


def _invalid(field: str, message: str) -> DeliveryValidationError:
    return DeliveryValidationError(message, {"problemas": [{"campo": field, "mensaje": message}]})


@dataclass(frozen=True, slots=True)
class ScheduleScope:
    """Quién arma o edita envíos programados y su tope.

    Attributes:
        owner: A nombre de quién quedan los nuevos (``username``).
        daily_limit: Corridas al día que puede sumar; ``None`` = sin tope.
        is_superuser: Si puede editar los envíos de otras personas.
    """

    owner: str
    daily_limit: int | None
    is_superuser: bool = False


class ManageSchedules:
    """Alta, edición y borrado de envíos programados."""

    def __init__(
        self,
        store: DeliveryScheduleStorePort,
        recipients: DeliveryStorePort,
        concepts: ConceptRepositoryPort,
        regions: RegionRepositoryPort,
    ) -> None:
        """Recibe las piezas.

        Args:
            store: Envíos programados.
            recipients: Correos de cada persona.
            concepts: Temas que se pueden buscar.
            regions: Catálogo de regiones.
        """
        self._store = store
        self._recipients = recipients
        self._concepts = concepts
        self._regions = regions

    async def create(self, data: ScheduleDraft, scope: ScheduleScope) -> DeliverySchedule:
        """Guarda un envío nuevo a nombre de quien lo pide.

        Args:
            data: El envío ya validado (``ScheduleDraft.validated``).
            scope: Dueño y tope.

        Raises:
            DeliveryValidationError: Tema, región o correo que no existen o
                no son suyos, o si pasa de su tope de corridas al día.
        """
        await self._check(data, scope.owner)
        check_daily_limit(data, await self._others(scope.owner, None), scope.daily_limit)
        return await self._store.create_schedule(data, scope.owner)

    async def update(
        self, schedule_id: int, data: ScheduleDraft, scope: ScheduleScope
    ) -> DeliverySchedule:
        """Reemplaza un envío; su dueño no cambia.

        El tope se revisa con los demás envíos del dueño. Un superusuario que
        edita el envío de otra persona no queda limitado por ese tope.

        Raises:
            DeliveryNotFoundError: Si no existe o no es de quien lo pide.
            DeliveryValidationError: Ver ``create``.
        """
        current = await self._store.get_schedule(schedule_id)
        if current is None:
            raise DeliveryNotFoundError("No existe ese envío programado.", {"id": schedule_id})
        await self._check(data, current.owner)
        if current.owner == scope.owner or not scope.is_superuser:
            others = await self._others(current.owner, schedule_id)
            check_daily_limit(data, others, scope.daily_limit)
        return await self._store.update_schedule(schedule_id, data)

    async def delete(self, schedule_id: int) -> None:
        """Borra un envío; lo que ya se mandó sigue en el historial.

        Raises:
            DeliveryNotFoundError: Si no existe o no es de quien lo pide.
        """
        if not await self._store.delete_schedule(schedule_id):
            raise DeliveryNotFoundError("No existe ese envío programado.", {"id": schedule_id})

    async def _others(self, owner: str, except_id: int | None) -> list[ScheduleDraft]:
        return [
            s.data
            for s in await self._store.list_schedules()
            if s.owner == owner and s.id != except_id
        ]

    async def _check(self, data: ScheduleDraft, owner: str) -> None:
        for concept_id in data.concept_ids:
            if await self._concepts.get(concept_id) is None:
                raise _invalid("concept_ids", "Uno de los temas ya no existe.")
        if await self._regions.get(data.region_id) is None:
            raise _invalid("region_id", "Esa región no existe.")
        for recipient_id in data.recipient_ids:
            recipient = await self._recipients.get_recipient(recipient_id)
            if recipient is None or recipient.owner != owner:
                raise _invalid("recipient_ids", "Elige solo correos de la lista.")


@dataclass(frozen=True, slots=True)
class StarterTemplate:
    """El envío con que empieza cada usuario nuevo (sale de la configuración).

    Attributes:
        name: Nombre del envío («Monitor FGR»).
        concept: Nombre del tema (``AUTOMATIC_CONCEPT``).
        region_code: Clave de la región (``AUTOMATIC_REGION_CODE``).
        schedule: Horas (``AUTOMATIC_RUN_HOURS``).
    """

    name: str
    concept: str
    region_code: str
    schedule: RunSchedule


class StarterSchedule:
    """Le da a una persona nueva su copia del monitor FGR, sin correos todavía."""

    def __init__(
        self,
        store: DeliveryScheduleStorePort,
        concepts: ConceptRepositoryPort,
        regions: RegionRepositoryPort,
        template: StarterTemplate,
    ) -> None:
        """Recibe las piezas y la plantilla."""
        self._store = store
        self._concepts = concepts
        self._regions = regions
        self._template = template

    async def give(self, owner: str) -> DeliverySchedule | None:
        """Crea el envío inicial de ``owner``.

        No se corre nada mientras no agregue un correo; si lo deja igual, se
        agrupa con los demás y no cuesta más.

        Returns:
            El envío creado, o ``None`` si falta el tema o la región de la
            plantilla (queda en los logs; la persona se crea igual).
        """
        concept_id = await find_concept_id(self._concepts, self._template.concept)
        region = await self._regions.get_by_code(self._template.region_code)
        if concept_id is None or region is None:
            logger.warning(
                "No se pudo dar el envío inicial",
                extra={
                    "owner": owner,
                    "concepto": self._template.concept,
                    "region": self._template.region_code,
                },
            )
            return None
        draft = ScheduleDraft(
            self._template.name, (concept_id,), region.id, self._template.schedule
        )
        return await self._store.create_schedule(draft, owner)


class PendingRuns:
    """¿Qué corridas tocan en este minuto? Las aparta y las agrupa."""

    def __init__(
        self,
        store: DeliveryScheduleStorePort,
        grace: timedelta,
        margin: timedelta = timedelta(0),
    ) -> None:
        """Recibe las piezas.

        Args:
            store: Envíos programados (todos: corre como el sistema).
            grace: Cuánto después de su hora todavía se lanza una corrida.
            margin: Tiempo extra antes del inicio de cada periodo.
        """
        self._store = store
        self._grace = grace
        self._margin = margin

    async def execute(self, now: datetime) -> list[DueRun]:
        """Las corridas que tocan, ya apartadas.

        Un envío sin correos no lanza nada: sería pagar a la IA para nadie.

        Args:
            now: Este momento (cualquier zona).

        Returns:
            Las corridas que hay que lanzar; las que otra revisión ya apartó
            no salen.
        """
        items = [
            ScheduledItem(s.id, s.data)
            for s in await self._store.list_schedules()
            if s.data.is_active and s.data.recipient_ids
        ]
        runs = due_runs(items, now.astimezone(MEXICO_CITY), self._grace, self._margin)
        return [run for run in runs if await self._store.claim_run(run.run_key)]


async def recipients_of(
    schedules: DeliveryScheduleStorePort,
    recipients: DeliveryStorePort,
    schedule_ids: Sequence[int],
) -> list[Recipient]:
    """Los correos a los que va una corrida: los de sus envíos, sin repetir.

    Args:
        schedules: Envíos programados.
        recipients: Correos.
        schedule_ids: Envíos que reciben la corrida.

    Returns:
        Los destinatarios activos, cada uno una vez.
    """
    found: dict[int, Recipient] = {}
    for schedule_id in schedule_ids:
        schedule = await schedules.get_schedule(schedule_id)
        if schedule is None or not schedule.data.is_active:
            continue
        for recipient_id in schedule.data.recipient_ids:
            recipient = await recipients.get_recipient(recipient_id)
            if recipient is not None and recipient.data.is_active:
                found[recipient.id] = recipient
    return list(found.values())
