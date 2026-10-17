"""Endpoints ``/api/v1/searches`` (especificación §13).

Routers delgados: reciben parámetros, toman las piezas que armó la
aplicación al arrancar (``app.state``) y llaman a un caso de uso.

- ``POST /searches/estimate``: qué se haría y cuánto costaría. No gasta.
- ``POST /searches``: lanza la búsqueda (``202``); el worker la corre.

No hace: no valida reglas de negocio; sus errores los traduce
``app.api.errors`` al formato uniforme.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.errors import ERROR_RESPONSES
from app.api.v1.concepts import get_actor
from app.api.v1.schemas.searches import EstimateOut, SearchIn, SearchStartedOut
from app.application.audit import Actor
from app.application.clock import mexico_city_today
from app.application.ports.search_queue import SearchQueuePort
from app.application.ports.search_store import SearchStorePort
from app.application.use_cases.plan_search import PlanSearch, SearchRequest
from app.application.use_cases.start_search import StartSearch

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
        actor.user_id, tuple(body.concept_ids), body.region_id, body.window(mexico_city_today())
    )


@router.post(
    "/estimate",
    response_model=EstimateOut,
    summary="Estimar una búsqueda sin gastar",
)
async def estimate_search(body: SearchIn, planner: Planner, actor: CurrentActor) -> EstimateOut:
    """Consultas que se harían, créditos de SearchApi y costo máximo de la IA."""
    return EstimateOut.from_estimate(await planner.estimate(_request(body, actor)))


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SearchStartedOut,
    summary="Lanzar una búsqueda",
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
