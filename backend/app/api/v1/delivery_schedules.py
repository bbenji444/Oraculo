"""Envíos programados («Mis envíos», ``/deliveries/schedules``, ADR-0046).

Cada persona arma los suyos: qué temas, de qué región, a qué horas, qué días
y a cuáles de sus correos. El superusuario ve y edita los de todos.

- ``GET /deliveries/schedules``: los envíos, cuántas corridas al día suma la
  persona, su tope y lo que cuesta una corrida;
- ``POST /deliveries/schedules``: uno nuevo;
- ``PUT``, ``DELETE /deliveries/schedules/{id}``: cambiarlo o borrarlo.

Quién ve qué lo decide la base (seguridad por filas, migración 0043).

No hace: ninguna regla de negocio; traduce entre HTTP y los casos de uso.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from pydantic import BaseModel, Field

from app.api.auth import CurrentUser
from app.api.errors import ERROR_RESPONSES, error_responses
from app.application.clock import MEXICO_CITY
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.deliveries import DeliveryStorePort
from app.application.ports.delivery_schedules import (
    DeliverySchedule,
    DeliveryScheduleStorePort,
)
from app.application.ports.regions import RegionRepositoryPort
from app.application.ports.schedule import ScheduleStorePort
from app.application.use_cases.delivery_schedules import ManageSchedules, ScheduleScope
from app.domain.access import AuthUser
from app.domain.delivery_schedules import (
    MAX_DAILY_RUNS_SUPERUSER,
    MAX_DAILY_RUNS_USER,
    ScheduleDraft,
    daily_runs,
)
from app.domain.schedule import format_time, parse_time

router = APIRouter(prefix="/deliveries/schedules", tags=["envíos"], responses=ERROR_RESPONSES)

# Próximas corridas que se muestran de cada envío.
UPCOMING_RUNS = 3
# Periodo con que se promedia el costo de una corrida (igual que «Horario»).
COST_WINDOW = timedelta(days=14)


class _Pieces:
    """Lo que necesita esta pantalla, sacado del estado de la app."""

    def __init__(self, request: Request) -> None:
        state = request.app.state
        self.schedules: DeliveryScheduleStorePort = state.delivery_schedule_store
        self.recipients: DeliveryStorePort = state.delivery_store
        self.concepts: ConceptRepositoryPort = state.concept_repository
        self.regions: RegionRepositoryPort = state.region_repository
        self.costs: ScheduleStorePort = state.schedule_store

    def manage(self) -> ManageSchedules:
        """El caso de uso con sus piezas."""
        return ManageSchedules(self.schedules, self.recipients, self.concepts, self.regions)


Pieces = Annotated[_Pieces, Depends(_Pieces)]
ScheduleId = Annotated[int, Path(description="Id del envío programado.")]


class ScheduleIn(BaseModel):
    """Un envío programado."""

    name: str = Field(min_length=1, max_length=80, examples=["Extorsión Jalisco tarde"])
    concept_ids: list[int] = Field(min_length=1, max_length=5, examples=[[3]])
    region_id: int = Field(examples=[14])
    times: list[str] = Field(
        min_length=1, max_length=8, examples=[["16:00", "20:00"]], description="«HH:MM», CDMX."
    )
    days: list[int] = Field(
        default_factory=list, description="1 = lunes … 7 = domingo; vacío = todos."
    )
    recipient_ids: list[int] = Field(
        default_factory=list, description="A cuáles de sus correos se manda."
    )
    is_active: bool = True

    def draft(self) -> ScheduleDraft:
        """Los datos validados.

        Raises:
            DeliveryValidationError: Si no cumplen las reglas.
            ScheduleValidationError: Si una hora no tiene forma «HH:MM».
        """
        return ScheduleDraft.validated(
            name=self.name,
            concept_ids=self.concept_ids,
            region_id=self.region_id,
            times=[parse_time(t) for t in self.times],
            days=self.days,
            recipient_ids=self.recipient_ids,
            is_active=self.is_active,
        )


class ScheduleOut(ScheduleIn):
    """Un envío programado guardado."""

    id: int
    owner: str = Field(examples=["benji"])
    concept_names: list[str] = Field(examples=[["Extorsión"]])
    region_name: str | None = Field(examples=["Jalisco"])
    runs_per_day: int = Field(description="Corridas en su día con más corridas.")
    upcoming: list[datetime] = Field(description="Próximas corridas (si está prendido).")


class ScheduleListOut(BaseModel):
    """Los envíos programados y el tope de la persona."""

    items: list[ScheduleOut]
    daily_runs: int = Field(description="Corridas al día que suman los envíos de la persona.")
    daily_limit: int = Field(description="Su tope de corridas al día.")
    average_run_cost_usd: float | None = Field(
        description="Costo promedio de una corrida en las últimas dos semanas (IA)."
    )


def _limit(user: AuthUser) -> int:
    return MAX_DAILY_RUNS_SUPERUSER if user.is_superuser else MAX_DAILY_RUNS_USER


def _scope(user: AuthUser) -> ScheduleScope:
    return ScheduleScope(user.username, _limit(user), user.is_superuser)


async def _out(schedule: DeliverySchedule, pieces: _Pieces) -> ScheduleOut:
    data = schedule.data
    names = []
    for concept_id in data.concept_ids:
        concept = await pieces.concepts.get(concept_id)
        names.append(concept.data.name if concept else f"Tema {concept_id} (borrado)")
    region = await pieces.regions.get(data.region_id)
    now = datetime.now(UTC).astimezone(MEXICO_CITY)
    return ScheduleOut(
        id=schedule.id,
        owner=schedule.owner,
        name=data.name,
        concept_ids=list(data.concept_ids),
        concept_names=names,
        region_id=data.region_id,
        region_name=region.name if region else None,
        times=[format_time(t) for t in data.schedule.times],
        days=list(data.schedule.days),
        recipient_ids=list(data.recipient_ids),
        is_active=data.is_active,
        runs_per_day=max(data.runs_per_day()),
        upcoming=data.schedule.upcoming(now, UPCOMING_RUNS) if data.is_active else [],
    )


@router.get("", response_model=ScheduleListOut, summary="Envíos programados")
async def list_schedules(pieces: Pieces, user: CurrentUser) -> ScheduleListOut:
    """Los envíos de la persona (el superusuario ve todos, con su dueño)."""
    schedules = await pieces.schedules.list_schedules()
    own = [s.data for s in schedules if s.owner == user.username]
    cost = await pieces.costs.average_run_cost(datetime.now(UTC) - COST_WINDOW)
    return ScheduleListOut(
        items=[await _out(s, pieces) for s in schedules],
        daily_runs=daily_runs(own),
        daily_limit=_limit(user),
        average_run_cost_usd=round(cost, 4) if cost is not None else None,
    )


@router.post(
    "",
    response_model=ScheduleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Programar un envío",
    responses=error_responses(422),
)
async def create_schedule(body: ScheduleIn, pieces: Pieces, user: CurrentUser) -> ScheduleOut:
    """Crea un envío a nombre de la persona.

    ``422 invalid_delivery`` con ``details.problemas`` si pasa de su tope de
    corridas al día (3 un usuario, 8 el superusuario) o si un dato no es válido.
    """
    created = await pieces.manage().create(body.draft(), _scope(user))
    return await _out(created, pieces)


@router.put(
    "/{schedule_id}",
    response_model=ScheduleOut,
    summary="Cambiar un envío programado",
    responses=error_responses(404, 422),
)
async def update_schedule(
    schedule_id: ScheduleId, body: ScheduleIn, pieces: Pieces, user: CurrentUser
) -> ScheduleOut:
    """Reemplaza el envío (también para apagarlo); aplica en el siguiente minuto."""
    updated = await pieces.manage().update(schedule_id, body.draft(), _scope(user))
    return await _out(updated, pieces)


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un envío programado",
    responses=error_responses(404),
)
async def delete_schedule(schedule_id: ScheduleId, pieces: Pieces) -> None:
    """Borra el envío; lo que ya se mandó sigue en el historial."""
    await pieces.manage().delete(schedule_id)
