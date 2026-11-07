"""Puerto del horario único de las corridas automáticas (ADR-0040).

``ScheduleStorePort`` guarda el horario que edita el administrador, marca qué
hora programada ya se lanzó y mide cuánto cuesta una corrida, para avisar en
la pantalla cuánto gasta cada hora extra.

No hace: ninguna regla del horario (eso es ``app.domain.schedule``).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.application.audit import AuditEntry
from app.domain.schedule import RunSchedule


@dataclass(frozen=True, slots=True)
class StoredSchedule:
    """El horario guardado y quién lo cambió por última vez."""

    schedule: RunSchedule
    updated_at: datetime
    updated_by: str


class ScheduleStorePort(Protocol):
    """Dónde vive el horario de las corridas."""

    async def get(self) -> StoredSchedule | None:
        """El horario guardado, o ``None`` si nadie lo ha editado todavía."""
        ...

    async def save(self, schedule: RunSchedule, audit: AuditEntry) -> StoredSchedule:
        """Reemplaza el horario y deja el cambio en la bitácora, en la misma transacción."""
        ...

    async def claim(self, slot: datetime) -> bool:
        """Aparta una hora programada para lanzar su corrida.

        Returns:
            ``True`` solo la primera vez para esa hora: así una corrida nunca
            se lanza dos veces aunque el reloj la vea en dos revisiones.
        """
        ...

    async def average_run_cost(self, since: datetime) -> float | None:
        """Costo promedio en dólares de las corridas automáticas desde ``since``.

        Suma la IA de la búsqueda y el resumen de su reporte; ``None`` si no hay corridas.
        """
        ...
