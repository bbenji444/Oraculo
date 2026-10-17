"""Endpoints **temporales** ``/api/v1/local-index`` (pestaña "Notas", ADR-0014).

Permiten ver en la interfaz, desde ya, las notas que junta la ingesta. La
Fase 5 los sustituye por la API definitiva de búsquedas (especificación §13).

Routers delgados: arman el caso de uso con lo que la aplicación creó al
arrancar y convierten el resultado.

No hace: no consulta SearchApi ni geolocaliza.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.errors import ERROR_RESPONSES
from app.api.v1.concepts import Concepts, Regions
from app.api.v1.schemas.local_index import IndexStatsOut, LocalIndexSearchOut
from app.application.ports.local_index import IndexStatsPort
from app.application.use_cases.concepts import PreviewConceptQueries
from app.application.use_cases.execute_queries import ExecuteQueries
from app.application.use_cases.local_index import SearchLocalIndex

router = APIRouter(
    prefix="/local-index", tags=["índice local (temporal)"], responses=ERROR_RESPONSES
)

# "Últimos 7 días": el rango de la historia H1.
DEFAULT_DAYS = 7


def get_local_executor(request: Request) -> ExecuteQueries:
    """``ExecuteQueries`` con solo el índice local, creado al arrancar.

    Args:
        request: Petición actual.

    Returns:
        El ejecutor compartido.
    """
    executor: ExecuteQueries = request.app.state.local_index_executor
    return executor


def get_index_stats(request: Request) -> IndexStatsPort:
    """Estadísticas del índice, creadas al arrancar.

    Args:
        request: Petición actual.

    Returns:
        El adaptador compartido.
    """
    stats: IndexStatsPort = request.app.state.index_stats
    return stats


Executor = Annotated[ExecuteQueries, Depends(get_local_executor)]
Stats = Annotated[IndexStatsPort, Depends(get_index_stats)]


def get_search(concepts: Concepts, regions: Regions, executor: Executor) -> SearchLocalIndex:
    """Arma el caso de uso con los repositorios y el ejecutor compartidos.

    Args:
        concepts: Repositorio de conceptos.
        regions: Repositorio de regiones.
        executor: Ejecutor del índice local.

    Returns:
        El caso de uso listo.
    """
    return SearchLocalIndex(PreviewConceptQueries(concepts, regions), executor)


Search = Annotated[SearchLocalIndex, Depends(get_search)]


@router.get("/search", response_model=LocalIndexSearchOut, summary="Buscar en el índice local")
async def search(
    use_case: Search,
    concept_id: Annotated[int, Query(description="Id del concepto.")],
    region_id: Annotated[int, Query(description="Región.")],
    days: Annotated[int, Query(description="Últimos N días (1 a 90).")] = DEFAULT_DAYS,
) -> LocalIndexSearchOut:
    """Notas del índice local para un concepto guardado (vista de prueba)."""
    result = await use_case.run(concept_id, region_id, days)
    return LocalIndexSearchOut.from_result(result)


@router.get("/stats", response_model=IndexStatsOut, summary="Resumen del índice local")
async def stats(index_stats: Stats) -> IndexStatsOut:
    """Notas por fuente, espacio en disco y última corrida de la ingesta."""
    return IndexStatsOut.from_stats(await index_stats.stats())
