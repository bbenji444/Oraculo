"""Casos de uso del horario único de las corridas (ADR-0040).

- ``GetSchedule``: el horario vigente, las próximas corridas y cuánto cuesta
  una corrida (para la pantalla «Envíos» y el Centro de mando).
- ``UpdateSchedule``: el administrador agrega, cambia o quita horas; aplica a
  todos y queda en la bitácora.
- ``DueRun``: lo usa el reloj cada minuto para saber si toca lanzar una
  corrida, y la aparta para que no se lance dos veces.

No hace: no lanza la corrida (eso es el worker) ni sabe de Celery.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.application.audit import SCHEDULE_UPDATED, Actor, AuditEntry
from app.application.clock import MEXICO_CITY
from app.application.ports.schedule import ScheduleStorePort
from app.domain.schedule import RunSchedule, format_time

# Próximas corridas que muestra la pantalla.
UPCOMING_RUNS = 5
# El costo promedio sale de las corridas de las últimas dos semanas: suficientes
# para promediar (≈ 40 corridas con 3 al día) y recientes para reflejar los
# precios y el volumen de notas actuales.
COST_WINDOW = timedelta(days=14)


@dataclass(frozen=True, slots=True)
class ScheduleView:
    """El horario como lo ve la pantalla.

    Attributes:
        schedule: Horas y días.
        is_default: ``True`` si nadie lo ha editado y vale ``AUTOMATIC_RUN_HOURS``.
        updated_at: Último cambio, o ``None`` si es el inicial.
        updated_by: Quién lo cambió, o ``None``.
        upcoming: Las próximas corridas (CDMX).
        average_run_cost_usd: Costo promedio de una corrida, o ``None`` sin datos.
    """

    schedule: RunSchedule
    is_default: bool
    updated_at: datetime | None
    updated_by: str | None
    upcoming: list[datetime]
    average_run_cost_usd: float | None


def _snapshot(schedule: RunSchedule) -> dict[str, object]:
    return {"times": [format_time(t) for t in schedule.times], "days": list(schedule.days)}


class GetSchedule:
    """El horario vigente."""

    def __init__(
        self,
        store: ScheduleStorePort,
        default: RunSchedule,
        clock: Callable[[], datetime],
    ) -> None:
        """Recibe las piezas.

        Args:
            store: Dónde está guardado.
            default: El horario inicial (``AUTOMATIC_RUN_HOURS``).
            clock: Hora actual en UTC.
        """
        self._store = store
        self._default = default
        self._clock = clock

    async def current(self) -> RunSchedule:
        """Solo las horas y días vigentes."""
        stored = await self._store.get()
        return stored.schedule if stored else self._default

    async def execute(self) -> ScheduleView:
        """El horario con sus próximas corridas y el costo promedio de una."""
        stored = await self._store.get()
        schedule = stored.schedule if stored else self._default
        now = self._clock()
        return ScheduleView(
            schedule=schedule,
            is_default=stored is None,
            updated_at=stored.updated_at if stored else None,
            updated_by=stored.updated_by if stored else None,
            upcoming=schedule.upcoming(now.astimezone(MEXICO_CITY), UPCOMING_RUNS),
            average_run_cost_usd=await self._store.average_run_cost(now - COST_WINDOW),
        )


class UpdateSchedule:
    """El administrador cambia el horario de todos."""

    def __init__(self, store: ScheduleStorePort, reader: GetSchedule) -> None:
        """Recibe el almacén y el lector (para el «antes» de la bitácora y la respuesta)."""
        self._store = store
        self._reader = reader

    async def execute(
        self, times: tuple[int, ...], days: tuple[int, ...], actor: Actor
    ) -> ScheduleView:
        """Reemplaza el horario.

        Args:
            times: Minutos del día (07:00 = 420).
            days: Días ISO (1 = lunes); vacío = todos.
            actor: Quién lo cambia.

        Returns:
            El horario nuevo, con sus próximas corridas.

        Raises:
            ScheduleValidationError: Ver ``RunSchedule.validated``.
        """
        schedule = RunSchedule.validated(times, days)
        before = await self._reader.current()
        await self._store.save(
            schedule,
            AuditEntry(
                actor,
                SCHEDULE_UPDATED,
                {"before": _snapshot(before), "after": _snapshot(schedule)},
            ),
        )
        return await self._reader.execute()


class DueRun:
    """¿Toca lanzar una corrida ahora? La aparta si sí."""

    def __init__(self, store: ScheduleStorePort, reader: GetSchedule, grace: timedelta) -> None:
        """Recibe las piezas.

        Args:
            store: Dónde se apartan las horas ya lanzadas.
            reader: El horario vigente.
            grace: Cuánto después de su hora todavía se lanza una corrida.
        """
        self._store = store
        self._reader = reader
        self._grace = grace

    async def execute(self, now: datetime) -> datetime | None:
        """La hora programada que toca lanzar, ya apartada.

        Args:
            now: Este momento (cualquier zona).

        Returns:
            La hora programada (CDMX), o ``None`` si no toca o ya se lanzó.
        """
        schedule = await self._reader.current()
        slot = schedule.due(now.astimezone(MEXICO_CITY), self._grace)
        if slot is None or not await self._store.claim(slot):
            return None
        return slot
