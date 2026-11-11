"""Rutas de los vínculos entre entidades de un caso (Fase 9.5, D6 a D9).

- ``GET /cases/{id}/relationships``: sugeridos, confirmados o descartados,
  con su origen, su confianza y las notas que los sostienen.
- ``POST /relationships``: el analista dibuja un vínculo (nace confirmado).
- ``POST /relationships/confirm`` y ``/discard``: revisar uno sugerido. Van
  con la llave (entidades y tipo) porque un sugerido por coocurrencia todavía
  no tiene id.
- ``POST /cases/{id}/relationships/review``: confirmar o descartar varios a
  la vez (F12, ADR-0107), todos o ninguno.

Cada ruta solo traduce HTTP ↔ casos de uso; permisos y reglas viven en
``app.application.use_cases.relationships``.

No hace: no propone vínculos con la IA.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.cases import CaseId, Cases, CurrentActor
from app.api.v1.entities import Entities
from app.api.v1.schemas.entities import BulkReviewOut
from app.api.v1.schemas.relationships import (
    CaseRelationshipsOut,
    RelationshipIn,
    RelationshipOut,
    RelationshipReviewIn,
    RelationshipsReviewIn,
)
from app.application.ports.relationships import RelationshipKey, RelationshipRepositoryPort
from app.application.use_cases.relationships import (
    CreateRelationship,
    ListRelationships,
    RelationshipInput,
    ReviewRelationship,
    ReviewRelationships,
)
from app.domain.investigation import ReviewStatus

router = APIRouter(tags=["vínculos"], responses=ERROR_RESPONSES)


def get_relationship_repository(request: Request) -> RelationshipRepositoryPort:
    """Repositorio creado al arrancar la aplicación (las pruebas lo reemplazan)."""
    repository: RelationshipRepositoryPort = request.app.state.relationship_repository
    return repository


Relationships = Annotated[RelationshipRepositoryPort, Depends(get_relationship_repository)]


@router.get(
    "/cases/{case_id}/relationships",
    response_model=CaseRelationshipsOut,
    summary="Vínculos de un caso",
    responses=error_responses(404),
)
async def list_relationships(
    cases: Cases,
    relationships: Relationships,
    actor: CurrentActor,
    case_id: CaseId,
    *,
    review_status: Annotated[
        ReviewStatus, Query(alias="status", description="suggested, confirmed o discarded.")
    ] = ReviewStatus.SUGGESTED,
) -> CaseRelationshipsOut:
    """Solo entre entidades confirmadas; los de más confianza primero."""
    view = await ListRelationships(cases, relationships).execute(case_id, actor, review_status)
    return CaseRelationshipsOut.from_view(view)


@router.post(
    "/relationships",
    response_model=RelationshipOut,
    summary="Dibujar un vínculo entre dos entidades confirmadas",
    responses=error_responses(403, 404, 409, 422),
)
async def create_relationship(
    body: RelationshipIn,
    cases: Cases,
    entities: Entities,
    relationships: Relationships,
    actor: CurrentActor,
) -> RelationshipOut:
    """Nace confirmado con la firma de quien lo dibuja. Si ya existía, se confirma ese."""
    data = RelationshipInput(body.entity_a, body.entity_b, body.type, body.custom_label, body.notes)
    view, _ = await CreateRelationship(cases, entities, relationships).execute(
        body.case_id, data, actor
    )
    return RelationshipOut.from_view(view)


async def _review(
    body: RelationshipReviewIn,
    cases: Cases,
    relationships: Relationships,
    actor: CurrentActor,
    status: ReviewStatus,
) -> RelationshipOut:
    key = RelationshipKey(body.entity_a, body.entity_b, body.type)
    view, _ = await ReviewRelationship(cases, relationships).execute(
        body.case_id, key, status, actor
    )
    return RelationshipOut.from_view(view)


@router.post(
    "/relationships/confirm",
    response_model=RelationshipOut,
    summary="Confirmar un vínculo sugerido",
    responses=error_responses(403, 404, 409, 422),
)
async def confirm_relationship(
    body: RelationshipReviewIn, cases: Cases, relationships: Relationships, actor: CurrentActor
) -> RelationshipOut:
    """Firma quién y cuándo, y va a la bitácora (``relationship.confirmed``)."""
    return await _review(body, cases, relationships, actor, ReviewStatus.CONFIRMED)


@router.post(
    "/relationships/discard",
    response_model=RelationshipOut,
    summary="Descartar un vínculo sugerido",
    responses=error_responses(403, 404, 409, 422),
)
async def discard_relationship(
    body: RelationshipReviewIn, cases: Cases, relationships: Relationships, actor: CurrentActor
) -> RelationshipOut:
    """Deja de sugerirse sin borrarse (``relationship.discarded``)."""
    return await _review(body, cases, relationships, actor, ReviewStatus.DISCARDED)


@router.post(
    "/cases/{case_id}/relationships/review",
    response_model=BulkReviewOut,
    summary="Confirmar o descartar varios vínculos a la vez",
    responses=error_responses(403, 404, 409, 422),
)
async def review_relationships(
    body: RelationshipsReviewIn,
    cases: Cases,
    relationships: Relationships,
    actor: CurrentActor,
    case_id: CaseId,
) -> BulkReviewOut:
    """Todos o ninguno, cada uno con su firma y su bitácora (``"bulk": true``)."""
    keys = [RelationshipKey(item.entity_a, item.entity_b, item.type) for item in body.items]
    result = await ReviewRelationships(cases, relationships).execute(
        case_id, body.status, keys, actor
    )
    return BulkReviewOut.from_result(result)
