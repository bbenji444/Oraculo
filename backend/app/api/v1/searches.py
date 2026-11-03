"""Endpoints ``/api/v1/searches`` (especificación §13).

Routers delgados: reciben parámetros, toman las piezas que armó la
aplicación al arrancar (``app.state``) y llaman a un caso de uso.

- ``POST /searches/estimate``: qué se haría y cuánto costaría. No gasta.
- ``POST /searches``: lanza la búsqueda (``202``); el worker la corre.
- ``GET /searches/{id}`` y ``GET /searches``: estado y avance, e historial.
- ``GET /searches/{id}/articles``: sus notas, con filtros y cursor.
- ``GET /searches/{id}/aggregates``: conteos por región para el mapa de calor.

No hace: no valida reglas de negocio; sus errores los traduce
``app.api.errors`` al formato uniforme.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.articles import Articles
from app.api.v1.concepts import get_actor
from app.api.v1.schemas.articles import AggregatesOut, ArticlePageOut
from app.api.v1.schemas.searches import (
    EstimateOut,
    SearchIn,
    SearchOut,
    SearchPageOut,
    SearchStartedOut,
)
from app.application.audit import Actor
from app.application.clock import mexico_city_today
from app.application.ports.search_queue import SearchQueuePort
from app.application.ports.search_reads import (
    ArticleFilters,
    InRegion,
    SearchReaderPort,
    SearchTrashPort,
)
from app.application.ports.search_store import SearchStorePort
from app.application.use_cases.plan_search import PlanSearch, SearchRequest
from app.application.use_cases.search_reads import (
    DEFAULT_ARTICLE_PAGE_SIZE,
    DEFAULT_PAGE_SIZE,
    GetAggregates,
    GetSearch,
    ListSearchArticles,
    ListSearches,
)
from app.application.use_cases.start_search import StartSearch
from app.application.use_cases.trash import DeleteSearch, RestoreSearch
from app.domain.aggregates import AggregateLevel

router = APIRouter(prefix="/searches", tags=["búsquedas"], responses=ERROR_RESPONSES)


def get_search_planner(request: Request) -> PlanSearch:
    """Planeación creada al arrancar la aplicación.

    Args:
        request: Petición actual.

    Returns:
        El caso de uso compartido.
    """
    planner: PlanSearch = request.app.state.search_planner
    return planner


def get_search_store(request: Request) -> SearchStorePort:
    """Repositorio de búsquedas creado al arrancar.

    Args:
        request: Petición actual.

    Returns:
        El repositorio compartido.
    """
    store: SearchStorePort = request.app.state.search_store
    return store


def get_search_queue(request: Request) -> SearchQueuePort:
    """Cola del worker (las pruebas la reemplazan por una en memoria).

    Args:
        request: Petición actual.

    Returns:
        La cola compartida.
    """
    queue: SearchQueuePort = request.app.state.search_queue
    return queue


Planner = Annotated[PlanSearch, Depends(get_search_planner)]
Searches = Annotated[SearchStorePort, Depends(get_search_store)]
Queue = Annotated[SearchQueuePort, Depends(get_search_queue)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


def get_start_search(
    request: Request, planner: Planner, searches: Searches, queue: Queue
) -> StartSearch:
    """Caso de uso para lanzar búsquedas con las piezas compartidas.

    Args:
        request: Petición actual (para ``MAX_QUERIES_PER_SEARCH``).
        planner: Planeación.
        searches: Repositorio de búsquedas.
        queue: Cola del worker.

    Returns:
        El caso de uso.
    """
    max_queries: int = request.app.state.max_queries_per_search
    return StartSearch(planner, searches, queue, max_queries)


Starter = Annotated[StartSearch, Depends(get_start_search)]


def _request(body: SearchIn, actor: Actor) -> SearchRequest:
    return SearchRequest(
        actor.user_id,
        tuple(body.concept_ids),
        body.region_id,
        body.window(mexico_city_today()),
        tuple(body.providers) if body.providers is not None else None,
        category_ids=tuple(body.category_ids),
    )


@router.post(
    "/estimate",
    response_model=EstimateOut,
    summary="Estimar una búsqueda sin gastar",
    responses=error_responses(404),
)
async def estimate_search(body: SearchIn, planner: Planner, actor: CurrentActor) -> EstimateOut:
    """Consultas que se harían, créditos de SearchApi y costo máximo de la IA."""
    return EstimateOut.from_estimate(await planner.estimate(_request(body, actor)))


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SearchStartedOut,
    summary="Lanzar una búsqueda",
    responses=error_responses(404, 409, 503),
)
async def start_search(body: SearchIn, starter: Starter, actor: CurrentActor) -> SearchStartedOut:
    """Crea la búsqueda y la manda al worker. Gasta créditos y tokens de la IA.

    Consulta su avance en ``GET /searches/{search_id}``. Responde ``409`` si
    pasaría el tope mensual de créditos y ``503`` si falta la llave de la IA;
    en esos casos no se crea nada.
    """
    started = await starter.execute(_request(body, actor))
    return SearchStartedOut(
        search_id=str(started.search_id),
        status="pending",
        estimate=EstimateOut.from_estimate(started.estimate),
    )


def get_search_reader(request: Request) -> SearchReaderPort:
    """Lecturas de búsquedas creadas al arrancar.

    Args:
        request: Petición actual.

    Returns:
        El lector compartido.
    """
    reader: SearchReaderPort = request.app.state.search_store
    return reader


Reader = Annotated[SearchReaderPort, Depends(get_search_reader)]
SearchId = Annotated[UUID, Path(description="Id de la búsqueda.")]


@router.get("", response_model=SearchPageOut, summary="Historial de búsquedas")
async def list_searches(
    reader: Reader,
    actor: CurrentActor,
    cursor: Annotated[str | None, Query(description="Cursor de la página anterior.")] = None,
    limit: Annotated[int, Query(description="Tamaño de página (1 a 100).")] = DEFAULT_PAGE_SIZE,
) -> SearchPageOut:
    """Búsquedas de la persona, de la más reciente a la más vieja."""
    page = await ListSearches(reader).execute(actor.user_id, cursor, limit)
    return SearchPageOut.from_page(page)


@router.get(
    "/{search_id}",
    response_model=SearchOut,
    summary="Estado y avance de una búsqueda",
    responses=error_responses(404),
)
async def get_search(reader: Reader, search_id: SearchId) -> SearchOut:
    """Estado, etapa actual, conteos, créditos y costo. Consúltala cada 2 s mientras corre."""
    return SearchOut.from_detail(await GetSearch(reader).execute(search_id))


def get_search_trash(request: Request) -> SearchTrashPort:
    """Eliminar y restaurar búsquedas (el mismo repositorio de búsquedas).

    Args:
        request: Petición actual.

    Returns:
        La papelera compartida.
    """
    trash: SearchTrashPort = request.app.state.search_store
    return trash


Trash = Annotated[SearchTrashPort, Depends(get_search_trash)]


@router.delete(
    "/{search_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar una búsqueda del historial",
    responses=error_responses(403, 404),
)
async def delete_search(trash: Trash, actor: CurrentActor, search_id: SearchId) -> Response:
    """La quita del historial de forma reversible; sus notas siguen en el sistema."""
    await DeleteSearch(trash).execute(search_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{search_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Devolver una búsqueda al historial (deshacer)",
    responses=error_responses(403, 404),
)
async def restore_search(trash: Trash, actor: CurrentActor, search_id: SearchId) -> Response:
    """La devuelve tal como estaba. Si no estaba eliminada, no cambia nada."""
    await RestoreSearch(trash).execute(search_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{search_id}/articles",
    response_model=ArticlePageOut,
    summary="Notas de una búsqueda",
    responses=error_responses(404),
)
async def list_search_articles(  # noqa: PLR0913 — un parámetro de URL por filtro, todo por nombre (*)
    reader: Reader,
    articles: Articles,
    search_id: SearchId,
    *,
    relevant: Annotated[
        Literal["true", "all"],
        Query(description="true: solo las relevantes para algún concepto; all: todas."),
    ] = "true",
    in_region: Annotated[
        InRegion | None,
        Query(description="true: dentro; false: fuera; none: sin ubicación."),
    ] = None,
    precision: Annotated[
        list[str] | None,
        Query(description="country, state, municipality, locality o unknown (se repite)."),
    ] = None,
    concept_id: Annotated[int | None, Query(description="Solo las de este concepto.")] = None,
    cursor: Annotated[str | None, Query(description="Cursor de la página anterior.")] = None,
    limit: Annotated[
        int, Query(description="Tamaño de página (1 a 200).")
    ] = DEFAULT_ARTICLE_PAGE_SIZE,
) -> ArticlePageOut:
    """Notas con resumen, conceptos, ubicación, precisión y confianza; la más reciente primero."""
    filters = ArticleFilters(
        relevant_only=relevant == "true",
        in_region=in_region,
        precisions=frozenset(precision or ()),
        concept_id=concept_id,
    )
    page = await ListSearchArticles(reader, articles).execute(search_id, filters, cursor, limit)
    return ArticlePageOut.from_page(page)


@router.get(
    "/{search_id}/aggregates",
    response_model=AggregatesOut,
    summary="Mapa de calor: notas por región",
    responses=error_responses(404),
)
async def search_aggregates(
    reader: Reader,
    articles: Articles,
    search_id: SearchId,
    level: Annotated[
        AggregateLevel, Query(description="country, state, municipality o locality.")
    ] = AggregateLevel.STATE,
    relevant: Annotated[
        Literal["true", "all"], Query(description="true: solo las relevantes; all: todas.")
    ] = "true",
) -> AggregatesOut:
    """Cuántas notas caen en cada región, con su centro, al nivel pedido."""
    filters = ArticleFilters(relevant_only=relevant == "true")
    view = await GetAggregates(reader, articles).execute(search_id, level, filters)
    return AggregatesOut.from_view(view)
