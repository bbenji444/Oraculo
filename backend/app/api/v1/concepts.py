"""Endpoints ``/api/v1/concepts`` (especificación §13).

Routers delgados: reciben parámetros, arman el ``Actor`` (la persona
que entró con su llave + IP) y llaman a un caso de uso. Las rutas ``/preview`` se
declaran antes que ``/{concept_id}`` para que FastAPI no las confunda.

No hace: no valida reglas de negocio; sus errores los traduce
``app.api.errors`` al formato uniforme.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from app.api.auth import client_ip, get_current_user
from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.regions import get_region_repository
from app.api.v1.schemas.concepts import (
    ConceptIn,
    ConceptOut,
    ConceptPageOut,
    ConceptPatch,
    QueryPreviewOut,
)
from app.application.audit import Actor
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.regions import RegionRepositoryPort
from app.application.use_cases.concepts import (
    DEFAULT_PAGE_SIZE,
    CreateConcept,
    DeleteConcept,
    GetConcept,
    ListConcepts,
    PreviewConceptQueries,
    UpdateConcept,
)
from app.application.use_cases.plan_search import PlanSearch
from app.domain.queries import Provider

router = APIRouter(prefix="/concepts", tags=["conceptos"], responses=ERROR_RESPONSES)

# "Últimos 7 días": el rango de la historia H1.
DEFAULT_PREVIEW_DAYS = 7


def get_concept_repository(request: Request) -> ConceptRepositoryPort:
    """Repositorio creado al arrancar la aplicación (las pruebas lo reemplazan).

    Args:
        request: Petición actual.

    Returns:
        El repositorio compartido.
    """
    repository: ConceptRepositoryPort = request.app.state.concept_repository
    return repository


def get_preview_providers(request: Request) -> tuple[Provider, ...]:
    """Proveedores que podría recibir una búsqueda real (configurados y ofrecidos).

    Sale de la misma planeación que usa ``POST /searches``, para que "Probar
    concepto" muestre lo que de verdad se mandaría (las pruebas lo reemplazan).

    Args:
        request: Petición actual.

    Returns:
        Los proveedores configurados que se ofrecen como fuente, en su orden.
    """
    planner: PlanSearch = request.app.state.search_planner
    return planner.offered_providers()


def get_actor(request: Request) -> Actor:
    """Quién hace la petición (la persona que reconoció el candado) y su IP.

    Args:
        request: Petición actual.

    Returns:
        El actor para la bitácora.

    Raises:
        AuthenticationRequiredError: Si la ruta no pasó por el candado.
    """
    return Actor(get_current_user(request).username, client_ip(request))


Concepts = Annotated[ConceptRepositoryPort, Depends(get_concept_repository)]
Regions = Annotated[RegionRepositoryPort, Depends(get_region_repository)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
ConceptId = Annotated[int, Path(description="Id del concepto.")]
RegionId = Annotated[int, Query(description="Región para la que se arman las consultas.")]
Days = Annotated[int, Query(description="Últimos N días (1 a 90).")]
PreviewProviders = Annotated[tuple[Provider, ...], Depends(get_preview_providers)]


def get_query_preview(
    concepts: Concepts, regions: Regions, providers: PreviewProviders
) -> PreviewConceptQueries:
    """Caso de uso "Probar concepto" con sus repositorios y proveedores.

    Args:
        concepts: Repositorio de conceptos.
        regions: Catálogo de regiones.
        providers: Proveedores que recibirían la búsqueda.

    Returns:
        El caso de uso listo.
    """
    return PreviewConceptQueries(concepts, regions, providers)


QueryPreview = Annotated[PreviewConceptQueries, Depends(get_query_preview)]


@router.get("", response_model=ConceptPageOut, summary="Lista de conceptos")
async def list_concepts(
    concepts: Concepts,
    active: Annotated[
        bool | None,
        Query(description="true: solo activos (panel de búsqueda); false: solo inactivos."),
    ] = None,
    cursor: Annotated[str | None, Query(description="Cursor de la página anterior.")] = None,
    limit: Annotated[int, Query(description="Tamaño de página (1 a 200).")] = DEFAULT_PAGE_SIZE,
) -> ConceptPageOut:
    """Conceptos vigentes en orden alfabético."""
    page = await ListConcepts(concepts).execute(active, cursor, limit)
    return ConceptPageOut.from_page(page)


@router.post(
    "",
    response_model=ConceptOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un concepto",
    responses=error_responses(409),
)
async def create_concept(body: ConceptIn, concepts: Concepts, actor: CurrentActor) -> ConceptOut:
    """Valida, guarda y registra en la bitácora."""
    concept = await CreateConcept(concepts).execute(body.to_input(), actor)
    return ConceptOut.from_domain(concept)


@router.post(
    "/preview",
    response_model=QueryPreviewOut,
    summary="Probar un concepto sin guardar",
    responses=error_responses(404),
)
async def preview_draft(
    body: ConceptIn,
    use_case: QueryPreview,
    region_id: RegionId,
    days: Days = DEFAULT_PREVIEW_DAYS,
) -> QueryPreviewOut:
    """Consultas que generaría el borrador, sin guardar nada ni gastar créditos."""
    preview = await use_case.for_draft(body.to_input(), region_id, days)
    return QueryPreviewOut.from_preview(preview)


@router.get(
    "/{concept_id}",
    response_model=ConceptOut,
    summary="Detalle de un concepto",
    responses=error_responses(404),
)
async def get_concept(concepts: Concepts, concept_id: ConceptId) -> ConceptOut:
    """Concepto vigente por id."""
    return ConceptOut.from_domain(await GetConcept(concepts).execute(concept_id))


@router.patch(
    "/{concept_id}",
    response_model=ConceptOut,
    summary="Editar un concepto",
    responses=error_responses(404, 409),
)
async def update_concept(
    body: ConceptPatch, concepts: Concepts, actor: CurrentActor, concept_id: ConceptId
) -> ConceptOut:
    """Cambia solo los campos enviados (también activar o desactivar)."""
    concept = await UpdateConcept(concepts).execute(concept_id, body.to_changes(), actor)
    return ConceptOut.from_domain(concept)


@router.delete(
    "/{concept_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar un concepto",
    responses=error_responses(404),
)
async def delete_concept(
    concepts: Concepts, actor: CurrentActor, concept_id: ConceptId
) -> Response:
    """Borrado lógico si el concepto ya se usó en búsquedas; físico si no."""
    await DeleteConcept(concepts).execute(concept_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{concept_id}/preview",
    response_model=QueryPreviewOut,
    summary="Probar un concepto guardado",
    responses=error_responses(404),
)
async def preview_saved(
    use_case: QueryPreview,
    concept_id: ConceptId,
    region_id: RegionId,
    days: Days = DEFAULT_PREVIEW_DAYS,
) -> QueryPreviewOut:
    """Consultas que generaría el concepto, sin gastar créditos (historia H2)."""
    preview = await use_case.for_saved(concept_id, region_id, days)
    return QueryPreviewOut.from_preview(preview)
