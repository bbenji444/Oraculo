"""Horario único de las corridas automáticas del monitor FGR (ADR-0031, ADR-0040).

Benji, 06/11/2026: hay **un solo horario para todos**, lo maneja el
administrador desde «Envíos» y a cada hora programada se hace una corrida
nueva (búsqueda + IA + PDF) que se manda a todos. Nada por usuario: cada
horario distinto sería otra corrida y más tokens.

Aquí viven las reglas de ese horario: qué horas valen (tope por día y
separación mínima), a qué corrida pertenece un momento, cuál es la anterior
(para que cada corrida cubra solo lo publicado desde ella) y cuál sigue.

No hace: no lee ni guarda el horario (eso es el repositorio), no programa
nada (eso es el reloj de Celery) ni convierte zonas horarias: recibe y
devuelve horas locales de la Ciudad de México.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.errors import InvalidRequestError, ScheduleValidationError

HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = HOURS_PER_DAY * MINUTES_PER_HOUR
DAYS_PER_WEEK = 7
# Días ISO: 1 = lunes … 7 = domingo.
FIRST_DAY = 1
LAST_DAY = DAYS_PER_WEEK
# Topes acordados con Benji (06/11/2026) para contener el consumo de tokens:
# cada hora es una corrida completa (≈ US$0.04 medidos en las corridas del
# 23/10 al 06/11) y una corrida tarda varios minutos, así que dos muy juntas
# se encimarían.
MAX_RUNS_PER_DAY = 8
MIN_GAP_MINUTES = 60
_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_run_hours(value: str) -> tuple[int, ...]:
    """Lee las horas iniciales de ``AUTOMATIC_RUN_HOURS`` («7,15,23»).

    Solo se usan mientras el administrador no guarde un horario en la pantalla.

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


def parse_time(value: str) -> int:
    """Convierte «09:30» en minutos del día (570).

    Args:
        value: Hora «HH:MM» de 24 horas.

    Returns:
        Minutos desde la medianoche.

    Raises:
        ScheduleValidationError: Si no es una hora válida.

    Example:
        >>> parse_time("9:30")
        570
    """
    match = _TIME.match(value.strip())
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour < HOURS_PER_DAY and minute < MINUTES_PER_HOUR:
            return hour * MINUTES_PER_HOUR + minute
    raise _invalid("times", f"«{value}» no es una hora válida (usa HH:MM, por ejemplo 07:30).")


def format_time(minutes: int) -> str:
    """Convierte minutos del día en «HH:MM».

    Example:
        >>> format_time(570)
        '09:30'
    """
    hour, minute = divmod(minutes, MINUTES_PER_HOUR)
    return f"{hour:02d}:{minute:02d}"


def _invalid(field: str, message: str) -> ScheduleValidationError:
    return ScheduleValidationError(message, {"problemas": [{"campo": field, "mensaje": message}]})


@dataclass(frozen=True, slots=True)
class RunWindow:
    """Las horas que cubre una corrida automática: de ``start`` a ``end``.

    Benji, 28/10/2026: cada corrida busca «estrictamente» lo publicado desde
    la corrida anterior. Con 07:00, 15:00 y 23:00, la de las 07:00 cubre de
    las 23:00 de ayer a las 07:00.

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


@dataclass(frozen=True, slots=True)
class RunSchedule:
    """El horario de las corridas: a qué horas y qué días.

    Attributes:
        times: Minutos del día (07:00 = 420), ordenados y sin repetir.
        days: Días ISO en que se corre (1 = lunes); vacío = todos los días.
    """

    times: tuple[int, ...]
    days: tuple[int, ...] = ()

    @classmethod
    def validated(cls, times: tuple[int, ...], days: tuple[int, ...] = ()) -> "RunSchedule":
        """Crea un horario que cumple las reglas, o explica qué falla.

        Args:
            times: Minutos del día, en cualquier orden y con repetidas.
            days: Días ISO; los siete juntos equivalen a «todos» (vacío).

        Returns:
            El horario ordenado.

        Raises:
            ScheduleValidationError: Sin horas, con horas fuera del día, con
                más de ``MAX_RUNS_PER_DAY`` o con dos horas a menos de
                ``MIN_GAP_MINUTES`` (también entre la última y la primera del
                día siguiente).

        Example:
            >>> RunSchedule.validated((900, 420, 900)).times
            (420, 900)
        """
        clean = tuple(sorted(set(times)))
        if not clean:
            raise _invalid("times", "Agrega al menos una hora.")
        if any(not 0 <= t < MINUTES_PER_DAY for t in clean):
            raise _invalid("times", "Cada hora debe estar entre 00:00 y 23:59.")
        if len(clean) > MAX_RUNS_PER_DAY:
            raise _invalid(
                "times",
                f"Máximo {MAX_RUNS_PER_DAY} horas al día: cada hora es una corrida con IA.",
            )
        # La última y la primera del día siguiente también deben separarse.
        pairs = zip(clean, (*clean[1:], clean[0] + MINUTES_PER_DAY), strict=True)
        for earlier, later in pairs:
            if len(clean) > 1 and later - earlier < MIN_GAP_MINUTES:
                raise _invalid(
                    "times",
                    f"Entre {format_time(earlier)} y {format_time(later % MINUTES_PER_DAY)} "
                    f"debe haber al menos {MIN_GAP_MINUTES} minutos: una corrida tarda "
                    "varios minutos y se encimarían.",
                )
        clean_days = tuple(sorted(set(days)))
        if any(not FIRST_DAY <= d <= LAST_DAY for d in clean_days):
            raise _invalid("days", "Los días van de 1 (lunes) a 7 (domingo).")
        return cls(clean, () if len(clean_days) == DAYS_PER_WEEK else clean_days)

    @classmethod
    def from_hours(cls, hours: tuple[int, ...]) -> "RunSchedule":
        """El horario a partir de horas enteras (``AUTOMATIC_RUN_HOURS``).

        Example:
            >>> RunSchedule.from_hours((7, 15, 23)).times
            (420, 900, 1380)
        """
        return cls(tuple(h * MINUTES_PER_HOUR for h in sorted(set(hours))))

    def runs_on(self, day: date) -> bool:
        """Si hay corridas ese día."""
        return not self.days or day.isoweekday() in self.days

    def slot_at_or_before(self, moment: datetime) -> datetime:
        """La corrida programada a la que pertenece un momento.

        Es la hora programada más reciente que ya llegó. Así, una corrida que
        el reloj lanzó a las 07:00:30 o que arrancó tarde a las 07:40 sigue
        siendo «la de las 07:00».

        Args:
            moment: Momento en hora de la Ciudad de México.

        Returns:
            La hora programada, con segundos en cero, en la misma zona.

        Example:
            >>> RunSchedule((420, 900)).slot_at_or_before(datetime(2026, 10, 26, 7, 40))
            datetime.datetime(2026, 10, 26, 7, 0)
        """
        minute = moment.hour * MINUTES_PER_HOUR + moment.minute
        start_of_day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        # Una semana y un día alcanzan para encontrar un día con corridas.
        for back in range(DAYS_PER_WEEK + 1):
            day = start_of_day - timedelta(days=back)
            if not self.runs_on(day.date()):
                continue
            earlier = [t for t in self.times if back > 0 or t <= minute]
            if earlier:
                return day + timedelta(minutes=earlier[-1])
        raise _invalid("times", "El horario no tiene horas.")

    def next_after(self, moment: datetime) -> datetime:
        """La siguiente corrida programada después de ``moment``.

        Example:
            >>> RunSchedule((420, 900)).next_after(datetime(2026, 10, 26, 7, 0))
            datetime.datetime(2026, 10, 26, 15, 0)
        """
        minute = moment.hour * MINUTES_PER_HOUR + moment.minute
        start_of_day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        for ahead in range(DAYS_PER_WEEK + 1):
            day = start_of_day + timedelta(days=ahead)
            if not self.runs_on(day.date()):
                continue
            later = [t for t in self.times if ahead > 0 or t > minute]
            if later:
                return day + timedelta(minutes=later[0])
        raise _invalid("times", "El horario no tiene horas.")

    def upcoming(self, moment: datetime, count: int) -> list[datetime]:
        """Las próximas ``count`` corridas después de ``moment``."""
        result: list[datetime] = []
        current = moment
        for _ in range(count):
            current = self.next_after(current)
            result.append(current)
        return result

    def previous(self, slot: datetime) -> datetime:
        """La corrida programada anterior a ``slot``.

        Example:
            >>> RunSchedule((420, 900, 1380)).previous(datetime(2026, 10, 28, 7, 0))
            datetime.datetime(2026, 10, 27, 23, 0)
        """
        return self.slot_at_or_before(slot - timedelta(minutes=1))

    def window(self, slot: datetime, margin: timedelta = timedelta(0)) -> RunWindow:
        """Las horas que cubre la corrida programada para ``slot``.

        Siempre desde la corrida programada anterior, aunque esa haya fallado:
        Benji pidió que cada corrida muestre solo «el periodo anterior al
        periodo actual» (28/10/2026).

        Args:
            slot: Hora programada de esta corrida.
            margin: Tiempo extra antes del inicio, para notas que los
                buscadores muestran tarde (0 = estricto, la decisión de Benji).

        Returns:
            La ventana de la corrida.
        """
        return RunWindow(self.previous(slot) - margin, slot)

    def due(self, now: datetime, grace: timedelta) -> datetime | None:
        """La corrida que toca lanzar ahora, si la hay.

        El reloj revisa cada minuto; con ``grace`` una revisión que se atrasó
        unos segundos (o un reinicio breve) no pierde la corrida.

        Args:
            now: Este momento (CDMX).
            grace: Cuánto después de su hora todavía se lanza una corrida.

        Returns:
            La hora programada, o ``None`` si ninguna llegó hace menos de ``grace``.
        """
        slot = self.slot_at_or_before(now)
        return slot if now - slot < grace else None
