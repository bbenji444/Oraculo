"""Rutas de la resolución de entidades de un caso (Fase 9.5, §9.8; ADR-0104).

- ``GET /cases/{id}/merge-suggestions``: pares que podrían ser la misma
  entidad, con su motivo. Mirarlos nunca fusiona.
- ``POST /entities/merge``: «Son la misma» (o «Unir con…»).
- ``POST /entities/merge/dismiss``: «No son la misma».
- ``POST /entities/{id}/unmerge``: deshacer una fusión.
- ``POST /entities/{id}/split``: separar menciones en una sugerencia nueva.

Cada ruta solo traduce HTTP ↔ casos de uso; permisos y reglas viven en
``app.application.use_cases.resolution``.

No hace: no crea vínculos (``app.api.v1.relationships``).
"""

from fastapi import APIRouter

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.cases import CaseId, Cases, CurrentActor
from app.api.v1.entities import Entities, EntityId
from app.api.v1.schemas.entities import EntityOut, ReviewIn
from app.api.v1.schemas.resolution import (
    DismissMergeIn,
    DismissOut,
    MergeIn,
    MergeSuggestionOut,
    MergeSuggestionsOut,
    SplitIn,
)
from app.application.use_cases.resolution import (
    DismissMerge,
    ListMergeSuggestions,
    MergeEntities,
    SplitEntity,
    UnmergeEntity,
)

router = APIRouter(tags=["entidades"], responses=ERROR_RESPONSES)


@router.get(
    "/cases/{case_id}/merge-suggestions",
    response_model=MergeSuggestionsOut,
    summary="Posibles duplicados de un caso",
    responses=error_responses(404),
)
async def list_merge_suggestions(
    cases: Cases, entities: Entities, actor: CurrentActor, case_id: CaseId
) -> MergeSuggestionsOut:
    """Pares del mismo tipo con el mismo nombre, un alias en común o nombres muy parecidos."""
    found = await ListMergeSuggestions(cases, entities).execute(case_id, actor)
    return MergeSuggestionsOut(items=[MergeSuggestionOut.from_proposal(p) for p in found])


@router.post(
    "/entities/merge",
    response_model=EntityOut,
    summary="Unir dos entidades que son la misma",
    responses=error_responses(403, 404, 409, 422),
)
async def merge_entities(
    body: MergeIn, cases: Cases, entities: Entities, actor: CurrentActor
) -> EntityOut:
    """Solo lo decide una persona. Se conserva el historial: se puede separar después."""
    kept = await MergeEntities(cases, entities).execute(
        body.case_id, body.keep_id, body.merge_id, actor
    )
    return EntityOut.from_entity(kept)


@router.post(
    "/entities/merge/dismiss",
    response_model=DismissOut,
    summary="Marcar que dos entidades no son la misma",
    responses=error_responses(403, 404, 409, 422),
)
async def dismiss_merge(
    body: DismissMergeIn, cases: Cases, entities: Entities, actor: CurrentActor
) -> DismissOut:
    """El par deja de sugerirse."""
    dismissed = await DismissMerge(cases, entities).execute(
        body.case_id, body.first_id, body.second_id, actor
    )
    return DismissOut(dismissed=dismissed)


@router.post(
    "/entities/{entity_id}/unmerge",
    response_model=EntityOut,
    summary="Separar una entidad de aquella a la que se unió",
    responses=error_responses(403, 404, 409, 422),
)
async def unmerge_entity(
    body: ReviewIn, cases: Cases, entities: Entities, actor: CurrentActor, entity_id: EntityId
) -> EntityOut:
    """Vuelve a ser independiente, con sus menciones."""
    separated = await UnmergeEntity(cases, entities).execute(body.case_id, entity_id, actor)
    return EntityOut.from_entity(separated)


@router.post(
    "/entities/{entity_id}/split",
    response_model=EntityOut,
    summary="Separar menciones en una sugerencia nueva",
    responses=error_responses(403, 404, 409, 422),
)
async def split_entity(
    body: SplitIn, cases: Cases, entities: Entities, actor: CurrentActor, entity_id: EntityId
) -> EntityOut:
    """Para cuando la agrupación juntó a dos personas con el mismo nombre. Responde la nueva."""
    created = await SplitEntity(cases, entities).execute(
        body.case_id, entity_id, body.mention_ids, actor
    )
    return EntityOut.from_entity(created)
