"""Puerto de los envíos programados (ADR-0046).

Lo implementa ``adapters/persistence/delivery_schedules_repository.py``. Con
el engine de la API, la seguridad por filas deja a cada persona ver y cambiar
solo sus envíos; el worker los ve todos.

No hace: ninguna regla (eso es ``domain/delivery_schedules``).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.delivery_schedules import ScheduleDraft


@dataclass(frozen=True, slots=True)
class DeliverySchedule:
    """Un envío programado guardado.

    Attributes:
        id: Id.
        owner: De quién es (``username``).
        data: Sus datos.
        updated_at: Último cambio.
    """

    id: int
    owner: str
    data: ScheduleDraft
    updated_at: datetime | None = None


class DeliveryScheduleStorePort(Protocol):
    """Dónde se guardan los envíos programados y las corridas apartadas."""

    async def list_schedules(self) -> list[DeliverySchedule]:
        """Los envíos que ve quien pregunta (todos, para el worker), por dueño y nombre.

        Nunca trae los de personas borradas.
        """
        ...

    async def get_schedule(self, schedule_id: int) -> DeliverySchedule | None:
        """Un envío por id (``None`` si no existe o no es de quien pregunta)."""
        ...

    async def create_schedule(self, data: ScheduleDraft, owner: str) -> DeliverySchedule:
        """Guarda un envío nuevo, con sus correos."""
        ...

    async def update_schedule(self, schedule_id: int, data: ScheduleDraft) -> DeliverySchedule:
        """Reemplaza los datos y los correos de un envío (su dueño no cambia)."""
        ...

    async def delete_schedule(self, schedule_id: int) -> bool:
        """Borra un envío; ``False`` si no existía."""
        ...

    async def claim_run(self, run_key: str) -> bool:
        """Aparta una corrida; ``False`` si ya la había apartado otra revisión."""
        ...

    async def set_topic(self, search_id: UUID, topic: str) -> None:
        """Anota qué buscó una corrida automática (``searches.topic_key``)."""
        ...
