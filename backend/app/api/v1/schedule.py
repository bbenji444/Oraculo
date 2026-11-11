"""Horario único de las corridas automáticas (``/schedule``, ADR-0040).

Un horario para todos: lo ven todos (cada quien elige de ahí a qué horas
recibe, ADR-0045) y solo el superusuario lo cambia. A cada
hora programada se hace una corrida nueva (búsqueda + IA + PDF) que cubre lo
publicado desde la hora anterior, y su reporte se manda a todos los
destinatarios activos. Cada hora extra es una corrida más: la respuesta trae
el costo promedio de una corrida para avisarlo en la pantalla.

- ``GET /schedule``: el horario, sus topes y las próximas corridas.
- ``PUT /schedule``: lo reemplaza (queda en la bitácora). Aplica en el
  siguiente minuto, sin reiniciar nada.

No hace: ninguna regla del horario; traduce entre HTTP y los casos de uso.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.auth import SuperUser
from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.concepts import get_actor
from app.application.audit import Actor
from app.application.use_cases.schedule import GetSchedule, ScheduleView, UpdateSchedule
from app.domain.schedule import MAX_RUNS_PER_DAY, MIN_GAP_MINUTES, format_time, parse_time

router = APIRouter(prefix="/schedule", tags=["horario"], responses=ERROR_RESPONSES)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def get_schedule_reader(request: Request) -> GetSchedule:
    """El lector del horario, con el horario inicial del ``.env``."""
    state = request.app.state
    return GetSchedule(state.schedule_store, state.schedule_default, _utc_now)


Reader = Annotated[GetSchedule, Depends(get_schedule_reader)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


class ScheduleIn(BaseModel):
    """El horario nuevo."""

    times: list[str] = Field(
        examples=[["07:00", "15:00", "23:00"]], description="Horas «HH:MM» de la Ciudad de México."
    )
    days: list[int] = Field(
        default_factory=list, description="1 = lunes … 7 = domingo; vacío = todos los días."
    )


class ScheduleLimitsOut(BaseModel):
    """Topes del horario, para que la pantalla avise antes de guardar."""

    max_runs_per_day: int = Field(examples=[MAX_RUNS_PER_DAY])
    min_gap_minutes: int = Field(examples=[MIN_GAP_MINUTES])


class ScheduleOut(ScheduleIn):
    """El horario vigente."""

    is_default: bool = Field(description="True si nadie lo ha editado (vale AUTOMATIC_RUN_HOURS).")
    enabled: bool = Field(description="Si el reloj lanza las corridas (AUTOMATIC_RUNS_ENABLED).")
    updated_at: datetime | None
    updated_by: str | None
    upcoming: list[datetime] = Field(description="Próximas corridas.")
    average_run_cost_usd: float | None = Field(
        description="Costo promedio de una corrida en las últimas dos semanas (IA)."
    )
    limits: ScheduleLimitsOut

    @classmethod
    def of(cls, view: ScheduleView, enabled: bool) -> "ScheduleOut":
        """Convierte del caso de uso."""
        return cls(
            times=[format_time(t) for t in view.schedule.times],
            days=list(view.schedule.days),
            is_default=view.is_default,
            enabled=enabled,
            updated_at=view.updated_at,
            updated_by=view.updated_by,
            upcoming=view.upcoming,
            average_run_cost_usd=(
                round(view.average_run_cost_usd, 4)
                if view.average_run_cost_usd is not None
                else None
            ),
            limits=ScheduleLimitsOut(
                max_runs_per_day=MAX_RUNS_PER_DAY, min_gap_minutes=MIN_GAP_MINUTES
            ),
        )


@router.get("", response_model=ScheduleOut, summary="Horario de las corridas")
async def get_schedule(request: Request, reader: Reader) -> ScheduleOut:
    """El horario vigente, sus topes, las próximas corridas y cuánto cuesta una."""
    return ScheduleOut.of(await reader.execute(), request.app.state.automatic_runs_enabled)


@router.put(
    "",
    response_model=ScheduleOut,
    summary="Cambiar el horario",
    responses=error_responses(422),
)
async def put_schedule(
    _: SuperUser, body: ScheduleIn, request: Request, reader: Reader, actor: CurrentActor
) -> ScheduleOut:
    """Reemplaza el horario de todos; aplica en el siguiente minuto.

    ``422 invalid_schedule`` con ``details.problemas`` si pasa de 8 horas al día
    o dos horas quedan a menos de 60 minutos.
    """
    view = await UpdateSchedule(request.app.state.schedule_store, reader).execute(
        tuple(parse_time(t) for t in body.times), tuple(body.days), actor
    )
    return ScheduleOut.of(view, request.app.state.automatic_runs_enabled)
