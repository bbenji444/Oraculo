"""Rutas del muro de un caso y de «Mis casos» en el globo (Fase 9.6, H9.3).

- ``GET /cases/map``: mis casos abiertos con su centro, para ponerlos en el
  globo. Va registrada antes que ``/cases/{id}`` para que "map" no se lea
  como un id.
- ``GET /cases/{id}/graph``: nodos con posición, arcos y constelación.
  Abrirlo cuenta como ver el caso (bitácora ``case.viewed``).

Cada ruta solo traduce HTTP ↔ casos de uso; permisos y reglas viven en
``app.application.use_cases.case_graph``.

No hace: no dibuja nada (eso es el frontend con MapLibre).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.cases import CaseId, Cases, CurrentActor
from app.api.v1.entities import Entities
from app.api.v1.relationships import Relationships
from app.api.v1.schemas.case_graph import CaseGraphOut, CaseOnMapOut, CasesOnMapOut
from app.application.ports.case_graph import CaseGraphRepositoryPort
from app.application.use_cases.case_graph import GetCaseGraph, ListCasesOnMap

router = APIRouter(tags=["casos"], responses=ERROR_RESPONSES)


def get_case_graph_repository(request: Request) -> CaseGraphRepositoryPort:
    """Repositorio creado al arrancar la aplicación (las pruebas lo reemplazan)."""
    repository: CaseGraphRepositoryPort = request.app.state.case_graph_repository
    return repository


def get_case_max_visible_nodes(request: Request) -> int:
    """Tope de nodos del muro (``CASE_MAX_VISIBLE_NODES``)."""
    limit: int = request.app.state.case_max_visible_nodes
    return limit


Points = Annotated[CaseGraphRepositoryPort, Depends(get_case_graph_repository)]
MaxNodes = Annotated[int, Depends(get_case_max_visible_nodes)]


@router.get("/cases/map", response_model=CasesOnMapOut, summary="Mis casos en el globo")
async def cases_on_map(points: Points, actor: CurrentActor) -> CasesOnMapOut:
    """Mis casos abiertos con al menos una nota ubicada, con su centro."""
    found = await ListCasesOnMap(points).execute(actor)
    return CasesOnMapOut(items=[CaseOnMapOut.from_case(c) for c in found])


@router.get(
    "/cases/{case_id}/graph",
    response_model=CaseGraphOut,
    summary="El muro de un caso para el globo",
    responses=error_responses(404),
)
async def case_graph(  # noqa: PLR0913 — una dependencia por fuente del muro, todas por nombre (*)
    cases: Cases,
    entities: Entities,
    relationships: Relationships,
    points: Points,
    max_nodes: MaxNodes,
    *,
    actor: CurrentActor,
    case_id: CaseId,
) -> CaseGraphOut:
    """Solo entidades confirmadas, con su posición; los arcos son los vínculos no descartados."""
    graph = await GetCaseGraph(
        cases=cases,
        entities=entities,
        relationships=relationships,
        points=points,
        max_nodes=max_nodes,
    ).execute(case_id, actor)
    return CaseGraphOut.from_graph(graph)
