"""Envíos programados: qué reporte, de dónde, a qué horas y a quién (ADR-0046).

Benji, 11/11/2026: «que los envíos sean totalmente moldeables y
personalizables»: cada persona arma los suyos («Extorsión en Jalisco, a las
16:00 y a las 20:00, de lunes a viernes»), y él también.

Aquí viven las reglas:

- un envío programado válido (``ScheduleDraft.validated``): nombre, temas,
  región, horas (las mismas reglas del horario: máximo 8 y una hora de
  separación) y días;
- el tope de corridas al día por persona (3 un usuario, 8 el superusuario),
  contando el día de la semana con más corridas;
- qué corridas tocan en este minuto y cómo se **agrupan**: dos envíos con los
  mismos temas, la misma región, la misma hora y el mismo periodo cubierto son
  una sola corrida con IA, que les llega a los dos (``due_runs``).

No hace: no guarda nada, no lanza corridas ni manda correos.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.errors import DeliveryValidationError, ScheduleValidationError
from app.domain.schedule import DAYS_PER_WEEK, FIRST_DAY, RunSchedule, RunWindow

# Topes acordados con Benji (10 y 11/11/2026): cada hora es una corrida con IA
# (≈ US$0.04). Se cuentan en el día de la semana con más corridas.
MAX_DAILY_RUNS_USER = 3
MAX_DAILY_RUNS_SUPERUSER = 8
MAX_SCHEDULE_NAME_CHARS = 80
# Temas por envío: más temas, más consultas y más notas para la IA.
MAX_CONCEPTS_PER_SCHEDULE = 5


def _invalid(field_name: str, message: str) -> DeliveryValidationError:
    return DeliveryValidationError(
        message, {"problemas": [{"campo": field_name, "mensaje": message}]}
    )


def topic_key(concept_ids: Iterable[int], region_id: int) -> str:
    """Qué busca una corrida, como texto comparable.

    Dos corridas con la misma llave son «la misma búsqueda»: sirve para
    agruparlas y para encontrar la anterior del mismo tema (el reporte separa
    lo nuevo de lo que ya se había mandado).

    Example:
        >>> topic_key([14, 3], 33)
        'c=3,14|r=33'
    """
    return f"c={','.join(str(c) for c in sorted(set(concept_ids)))}|r={region_id}"


@dataclass(frozen=True, slots=True)
class ScheduleDraft:
    """Los datos de un envío programado.

    Attributes:
        name: Cómo lo llama la persona («Extorsión Jalisco tarde»).
        concept_ids: Temas (conceptos) que se buscan.
        region_id: Dónde (país, estado o municipio).
        schedule: Horas y días.
        recipient_ids: A qué correos de la persona se manda.
        is_active: Si está prendido.
    """

    name: str
    concept_ids: tuple[int, ...]
    region_id: int
    schedule: RunSchedule
    recipient_ids: tuple[int, ...] = ()
    is_active: bool = True

    @property
    def topic(self) -> str:
        """Ver :func:`topic_key`."""
        return topic_key(self.concept_ids, self.region_id)

    def runs_per_day(self) -> tuple[int, ...]:
        """Corridas que hace cada día de la semana (lunes primero); 0 si está apagado."""
        if not self.is_active:
            return (0,) * DAYS_PER_WEEK
        count = len(self.schedule.times)
        return tuple(
            count if not self.schedule.days or day in self.schedule.days else 0
            for day in range(FIRST_DAY, FIRST_DAY + DAYS_PER_WEEK)
        )

    @classmethod
    def validated(  # noqa: PLR0913 — los campos del envío, por nombre (*)
        cls,
        *,
        name: str,
        concept_ids: Sequence[int],
        region_id: int,
        times: Sequence[int],
        days: Sequence[int] = (),
        recipient_ids: Sequence[int] = (),
        is_active: bool = True,
    ) -> "ScheduleDraft":
        """Limpia y valida un envío programado.

        Args:
            name: Nombre.
            concept_ids: Temas, al menos uno.
            region_id: Región.
            times: Minutos del día (16:00 = 960).
            days: Días ISO (1 = lunes); vacío = todos.
            recipient_ids: Correos de la persona a los que se manda.
            is_active: Si está prendido.

        Returns:
            El envío limpio (horas en orden, sin repetidos).

        Raises:
            DeliveryValidationError: Sin nombre, sin temas, con demasiados
                temas o con horas o días que no cumplen las reglas del horario.
        """
        clean_name = " ".join(name.split())
        if not clean_name:
            raise _invalid("name", "Ponle un nombre al envío.")
        if len(clean_name) > MAX_SCHEDULE_NAME_CHARS:
            raise _invalid("name", f"Máximo {MAX_SCHEDULE_NAME_CHARS} caracteres.")
        concepts = tuple(sorted(set(concept_ids)))
        if not concepts:
            raise _invalid("concept_ids", "Elige al menos un tema.")
        if len(concepts) > MAX_CONCEPTS_PER_SCHEDULE:
            raise _invalid("concept_ids", f"Máximo {MAX_CONCEPTS_PER_SCHEDULE} temas por envío.")
        try:
            schedule = RunSchedule.validated(tuple(times), tuple(days))
        except ScheduleValidationError as error:
            # Mismo código de error que el resto de «Envíos», para que la
            # pantalla ponga cada mensaje junto a su campo.
            raise DeliveryValidationError(str(error), error.details) from error
        return cls(
            clean_name,
            concepts,
            region_id,
            schedule,
            tuple(sorted(set(recipient_ids))),
            is_active,
        )


def daily_runs(drafts: Iterable[ScheduleDraft]) -> int:
    """Corridas del día de la semana con más corridas, sumando los envíos.

    Example:
        >>> diario = ScheduleDraft("A", (1,), 9, RunSchedule((420, 900)))
        >>> lunes = ScheduleDraft("B", (1,), 9, RunSchedule((600,), (1,)))
        >>> daily_runs([diario, lunes])
        3
    """
    totals = [0] * DAYS_PER_WEEK
    for draft in drafts:
        for day, runs in enumerate(draft.runs_per_day()):
            totals[day] += runs
    return max(totals)


def check_daily_limit(
    draft: ScheduleDraft, others: Iterable[ScheduleDraft], limit: int | None
) -> None:
    """Revisa que la persona no pase de su tope de corridas al día.

    Args:
        draft: El envío que se guarda.
        others: Los demás envíos de la misma persona.
        limit: Su tope; ``None`` = sin tope.

    Raises:
        DeliveryValidationError: Si con este envío pasa del tope.
    """
    if limit is None:
        return
    total = daily_runs([draft, *others])
    if total > limit:
        raise _invalid(
            "times",
            f"Puedes tener hasta {limit} corridas al día sumando todos tus envíos "
            f"(con este serían {total}). Cada hora es un reporte nuevo con IA.",
        )


@dataclass(frozen=True, slots=True)
class ScheduledItem:
    """Un envío prendido, como lo ve el reloj.

    Attributes:
        schedule_id: Id del envío.
        draft: Sus datos.
    """

    schedule_id: int
    draft: ScheduleDraft


@dataclass(frozen=True, slots=True)
class DueRun:
    """Una corrida que toca lanzar, con los envíos que la reciben.

    Attributes:
        topic: Ver :func:`topic_key`.
        concept_ids: Temas.
        region_id: Región.
        window: Periodo que cubre (desde la corrida anterior del envío).
        schedule_ids: Envíos programados a los que les llega.
    """

    topic: str
    concept_ids: tuple[int, ...]
    region_id: int
    window: RunWindow
    schedule_ids: tuple[int, ...] = field(default=())

    @property
    def slot(self) -> datetime:
        """La hora programada (fin de la ventana)."""
        return self.window.end

    @property
    def run_key(self) -> str:
        """Llave para apartar la corrida y no lanzarla dos veces.

        Example:
            >>> from app.domain.schedule import RunWindow
            >>> w = RunWindow(datetime(2026, 11, 11, 16), datetime(2026, 11, 11, 20))
            >>> DueRun("c=3|r=9", (3,), 9, w).run_key
            'c=3|r=9|2026-11-11T16:00|2026-11-11T20:00'
        """
        start = self.window.start.strftime("%Y-%m-%dT%H:%M")
        end = self.window.end.strftime("%Y-%m-%dT%H:%M")
        return f"{self.topic}|{start}|{end}"


def due_runs(
    items: Iterable[ScheduledItem],
    now: datetime,
    grace: timedelta,
    margin: timedelta = timedelta(0),
) -> list[DueRun]:
    """Las corridas que tocan en este momento, agrupadas.

    Cada envío prendido que llegó a una de sus horas (hace menos de
    ``grace``) pide una corrida que cubre desde su hora anterior. Los que
    piden lo mismo (temas, región y periodo) comparten una sola.

    Args:
        items: Envíos prendidos.
        now: Este momento, en hora de la Ciudad de México.
        grace: Cuánto después de su hora todavía se lanza.
        margin: Tiempo extra antes del inicio de cada periodo.

    Returns:
        Las corridas, en orden de llave.
    """
    groups: dict[str, DueRun] = {}
    for item in items:
        draft = item.draft
        if not draft.is_active:
            continue
        slot = draft.schedule.due(now, grace)
        if slot is None:
            continue
        run = DueRun(
            draft.topic, draft.concept_ids, draft.region_id, draft.schedule.window(slot, margin)
        )
        current = groups.get(run.run_key, run)
        groups[run.run_key] = DueRun(
            current.topic,
            current.concept_ids,
            current.region_id,
            current.window,
            (*current.schedule_ids, item.schedule_id),
        )
    return [groups[key] for key in sorted(groups)]
