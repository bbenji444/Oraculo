"""Rutas de las entidades de un caso (Fase 9.4, historia H9.2).

- ``GET /cases/{id}/entities``: sugeridas, confirmadas o descartadas, con su
  cita y la nota de donde salieron, y en qué va la lectura de la IA.
- ``POST /cases/{id}/extract``: "Analizar pendientes" (encola en el worker).
- ``POST /entities/{id}/confirm`` y ``/discard``: la revisión de una persona,
  firmada y en la bitácora.
- ``POST /cases/{id}/entities/review``: confirmar o descartar varias a la vez
  (F12, ADR-0107), todas o ninguna.

Cada ruta solo traduce HTTP ↔ casos de uso; permisos y reglas viven en
``app.application.use_cases.entities``.

No hace: no une ni vincula entidades (``resolution.py`` y ``relationships.py``, 9.5).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.cases import CaseId, Cases, CurrentActor
from app.api.v1.schemas.entities import (
    BulkReviewOut,
    CaseEntitiesOut,
    ConfirmIn,
    EntitiesReviewIn,
    EntityOut,
    ExtractOut,
    ReviewIn,
)
from app.application.ports.entities import EntityRepositoryPort
from app.application.use_cases.entities import (
    AnalyzePending,
    ConfirmEntity,
    DiscardEntity,
    EntityDecision,
    ListCaseEntities,
    QueueExtraction,
    ReviewEntities,
)
from app.application.use_cases.reports import LLMPrices
from app.domain.investigation import ReviewStatus

router = APIRouter(tags=["entidades"], responses=ERROR_RESPONSES)


def get_entity_repository(request: Request) -> EntityRepositoryPort:
    """Repositorio creado al arrancar la aplicación (las pruebas lo reemplazan)."""
    repository: EntityRepositoryPort = request.app.state.entity_repository
    return repository


def get_extraction_queue(request: Request) -> QueueExtraction:
    """Quien manda notas al worker (las pruebas lo reemplazan)."""
    queue: QueueExtraction = request.app.state.extraction_queue
    return queue


def get_llm_prices(request: Request) -> LLMPrices | None:
    """Precios de la IA configurada, para estimar antes de gastar."""
    prices: LLMPrices | None = request.app.state.llm_prices
    return prices


Entities = Annotated[EntityRepositoryPort, Depends(get_entity_repository)]
Queue = Annotated[QueueExtraction, Depends(get_extraction_queue)]
Prices = Annotated[LLMPrices | None, Depends(get_llm_prices)]
EntityId = Annotated[int, Path(description="Id de la entidad.")]


@router.get(
    "/cases/{case_id}/entities",
    response_model=CaseEntitiesOut,
    summary="Entidades de un caso",
    responses=error_responses(404),
)
async def list_case_entities(  # noqa: PLR0913 — dependencias y filtro, todo por nombre (*)
    cases: Cases,
    entities: Entities,
    prices: Prices,
    actor: CurrentActor,
    case_id: CaseId,
    *,
    review_status: Annotated[
        ReviewStatus, Query(alias="status", description="suggested, confirmed o discarded.")
    ] = ReviewStatus.SUGGESTED,
) -> CaseEntitiesOut:
    """Las del estado pedido (las de más menciones primero), conteos y avance de la IA."""
    view = await ListCaseEntities(cases, entities, prices).execute(case_id, actor, review_status)
    return CaseEntitiesOut.from_view(view)


@router.post(
    "/cases/{case_id}/extract",
    response_model=ExtractOut,
    summary="Analizar con la IA las notas pendientes del caso",
    responses=error_responses(403, 404, 409),
)
async def extract_case_entities(  # noqa: PLR0913 — una dependencia por pieza, todo por nombre (*)
    cases: Cases,
    entities: Entities,
    queue: Queue,
    prices: Prices,
    *,
    actor: CurrentActor,
    case_id: CaseId,
) -> ExtractOut:
    """Encola las notas pendientes o fallidas. Gasta tokens de la IA: responde el estimado."""
    result = await AnalyzePending(cases, entities, queue, prices).execute(case_id, actor)
    return ExtractOut.from_request(result)


@router.post(
    "/entities/{entity_id}/confirm",
    response_model=EntityOut,
    summary="Confirmar una entidad sugerida",
    responses=error_responses(403, 404, 409, 422),
)
async def confirm_entity(
    body: ConfirmIn, cases: Cases, entities: Entities, actor: CurrentActor, entity_id: EntityId
) -> EntityOut:
    """Firma quién y cuándo. Una persona exige su estatus legal según la nota; nunca "culpable"."""
    legal = body.legal_status.value if body.legal_status else None
    entity, _ = await ConfirmEntity(cases, entities).execute(body.case_id, entity_id, legal, actor)
    return EntityOut.from_entity(entity)


@router.post(
    "/entities/{entity_id}/discard",
    response_model=EntityOut,
    summary="Descartar una entidad sugerida",
    responses=error_responses(403, 404, 409),
)
async def discard_entity(
    body: ReviewIn, cases: Cases, entities: Entities, actor: CurrentActor, entity_id: EntityId
) -> EntityOut:
    """Deja de proponerse, sin borrarla: su evidencia se conserva."""
    entity, _ = await DiscardEntity(cases, entities).execute(body.case_id, entity_id, actor)
    return EntityOut.from_entity(entity)


@router.post(
    "/cases/{case_id}/entities/review",
    response_model=BulkReviewOut,
    summary="Confirmar o descartar varias entidades a la vez",
    responses=error_responses(403, 404, 409, 422),
)
async def review_entities(
    body: EntitiesReviewIn, cases: Cases, entities: Entities, actor: CurrentActor, case_id: CaseId
) -> BulkReviewOut:
    """Todas o ninguna, cada una con su firma y su bitácora. Personas: el estatus de su renglón."""
    decisions = [
        EntityDecision(item.entity_id, item.legal_status.value if item.legal_status else None)
        for item in body.items
    ]
    result = await ReviewEntities(cases, entities).execute(case_id, body.status, decisions, actor)
    return BulkReviewOut.from_result(result)
