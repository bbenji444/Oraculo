"""Horarios de las corridas automáticas del monitor FGR (F12.8, ADR-0031).

Benji fijó las corridas a las 07:00, 15:00 y 23:00 de la Ciudad de México.
Aquí se leen y validan esos horarios y se calcula a qué corrida pertenece un
momento (para mostrar «Corrida de las 07:00» aunque haya empezado tarde).

No hace: no programa nada (eso es el reloj de Celery) ni sabe de zonas
horarias: recibe y devuelve horas locales de la Ciudad de México.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.errors import InvalidRequestError

HOURS_PER_DAY = 24


def parse_run_hours(value: str) -> tuple[int, ...]:
    """Lee los horarios de ``AUTOMATIC_RUN_HOURS`` («7,15,23»).

    Args:
        value: Horas del día (0 a 23) separadas por coma.

    Returns:
        Las horas sin repetir, de la más temprana a la más tarde.

    Raises:
        InvalidRequestError: Si está vacío o alguna hora no es de 0 a 23.

    Example:
        >>> parse_run_hours("23, 7,15")
        (7, 15, 23)
    """
    try:
        hours = {int(part) for part in value.split(",") if part.strip()}
    except ValueError as error:
        raise InvalidRequestError(
            f"Los horarios deben ser horas separadas por coma («7,15,23»), no «{value}»."
        ) from error
    if not hours or any(not 0 <= h < HOURS_PER_DAY for h in hours):
        raise InvalidRequestError(f"Cada horario debe ser una hora de 0 a 23: «{value}».")
    return tuple(sorted(hours))


def run_slot(now: datetime, hours: tuple[int, ...]) -> datetime:
    """La corrida programada a la que pertenece un momento.

    Es la hora programada más reciente que ya pasó (ese mismo día o el día
    anterior). Así, una corrida que el reloj lanzó a las 07:00:03 o que
    arrancó tarde a las 07:40 sigue siendo «la de las 07:00».

    Args:
        now: Momento en hora de la Ciudad de México.
        hours: Horarios (``parse_run_hours``).

    Returns:
        La hora programada, con minutos y segundos en cero, en la misma zona.

    Example:
        >>> run_slot(datetime(2026, 10, 26, 7, 40), (7, 15, 23))
        datetime.datetime(2026, 10, 26, 7, 0)
    """
    start_of_hour = now.replace(minute=0, second=0, microsecond=0)
    earlier_today = [h for h in hours if h <= now.hour]
    if earlier_today:
        return start_of_hour.replace(hour=earlier_today[-1])
    # Antes de la primera del día: es la última de ayer.
    return (start_of_hour - timedelta(days=1)).replace(hour=hours[-1])


def utc_hours(hours: tuple[int, ...], utc_offset_hours: int) -> tuple[int, ...]:
    """Las mismas horas en UTC, para el reloj de Celery (que trabaja en UTC).

    Args:
        hours: Horas locales.
        utc_offset_hours: Diferencia de la zona local con UTC (CDMX: -6, sin
            horario de verano desde 2022).

    Returns:
        Las horas en UTC, ordenadas.

    Example:
        >>> utc_hours((7, 15, 23), -6)
        (5, 13, 21)
    """
    return tuple(sorted((h - utc_offset_hours) % HOURS_PER_DAY for h in hours))


@dataclass(frozen=True, slots=True)
class RunWindow:
    """Las horas que cubre una corrida automática: de ``start`` a ``end``.

    Benji, 28/10/2026: cada corrida busca «estrictamente» lo publicado desde
    la corrida anterior. La de las 07:00 cubre de las 23:00 de ayer a las
    07:00; la de las 15:00, de 07:00 a 15:00; la de las 23:00, de 15:00 a
    23:00. Antes cada corrida pedía «hoy y ayer» y volvía a traer lo de un día
    entero.

    Attributes:
        start: Primer momento incluido.
        end: Hora programada de la corrida (no incluida: lo publicado justo
            a esa hora es de la corrida siguiente).
    """

    start: datetime
    end: datetime

    def contains(self, moment: datetime | None) -> bool:
        """Si una nota publicada en ``moment`` le toca a esta corrida.

        Una nota sin fecha de publicación no le toca a ninguna: no se puede
        saber si ya salió en otra corrida.

        Args:
            moment: Fecha de publicación (con zona horaria), o ``None``.

        Returns:
            ``True`` si cae dentro de la ventana.
        """
        return moment is not None and self.start <= moment < self.end


def previous_slot(slot: datetime, hours: tuple[int, ...]) -> datetime:
    """La corrida programada anterior a ``slot``.

    Example:
        >>> previous_slot(datetime(2026, 10, 28, 7, 0), (7, 15, 23))
        datetime.datetime(2026, 10, 27, 23, 0)
    """
    return run_slot(slot - timedelta(minutes=1), hours)


def run_window(
    slot: datetime,
    hours: tuple[int, ...],
    margin: timedelta = timedelta(0),
) -> RunWindow:
    """Las horas que cubre la corrida programada para ``slot``.

    Siempre de la corrida programada anterior a esta, aunque la anterior no
    haya terminado. Antes, si una fallaba, la siguiente cubría desde la
    última que sí terminó y traía notas de otro periodo; Benji pidió que cada
    corrida muestre solo «el periodo anterior al periodo actual»
    (28/10/2026).

    Args:
        slot: Hora programada de esta corrida.
        hours: Horarios de las corridas (``parse_run_hours``).
        margin: Tiempo extra antes del inicio, para notas que los buscadores
            muestran tarde (0 = estricto, la decisión de Benji).

    Returns:
        La ventana de la corrida.

    Example:
        >>> run_window(datetime(2026, 10, 28, 7), (7, 15, 23)).start
        datetime.datetime(2026, 10, 27, 23, 0)
    """
    return RunWindow(previous_slot(slot, hours) - margin, slot)
