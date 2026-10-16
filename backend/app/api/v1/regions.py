"""Endpoints ``/api/v1/regions`` (especificación §13).

Routers delgados: reciben parámetros, llaman a un caso de uso y devuelven
el esquema. ``/search`` y ``/at`` se declaran antes de ``/{region_id}`` para
que FastAPI no los confunda con un id.

No hace: no valida reglas de negocio (límites, coordenadas): eso es de los
casos de uso, y sus errores los traduce ``app.api.errors``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.api.errors import ERROR_RESPONSES
from app.api.v1.schemas.regions import (
    LevelLiteral,
    RegionDetailOut,
    RegionListOut,
    RegionOut,
    RegionPageOut,
)
from app.application.ports.regions import RegionRepositoryPort
from app.application.use_cases.regions import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_SEARCH_LIMIT,
    FindRegionAtPoint,
    GetRegion,
    ListChildren,
    ListRegions,
    SearchRegions,
)
from app.domain.region import RegionLevel

router = APIRouter(prefix="/regions", tags=["regiones"], responses=ERROR_RESPONSES)


def get_region_repository(request: Request) -> RegionRepositoryPort:
    """Repositorio creado al arrancar la aplicación (las pruebas lo reemplazan).

    Args:
        request: Petición actual.

    Returns:
        El repositorio compartido.
    """
    repository: RegionRepositoryPort = request.app.state.region_repository
    return repository


Repository = Annotated[RegionRepositoryPort, Depends(get_region_repository)]
Cursor = Annotated[str | None, Query(description="Cursor devuelto por la página anterior.")]
Limit = Annotated[int, Query(description="Tamaño de página (1 a 200).")]


@router.get("", response_model=RegionPageOut, summary="Regiones de un nivel")
async def list_regions(
    repository: Repository,
    level: Annotated[LevelLiteral, Query(description="country, state, municipality o locality")],
    cursor: Cursor = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
) -> RegionPageOut:
    """Lista las regiones de un nivel en orden alfabético, por páginas."""
    page = await ListRegions(repository).execute(RegionLevel(level), cursor, limit)
    return RegionPageOut.from_page(page)


@router.get("/search", response_model=RegionListOut, summary="Buscar por nombre o alias")
async def search_regions(
    repository: Repository,
    q: Annotated[str, Query(description='Texto a buscar, por ejemplo "izta" o "cdmx".')],
    limit: Annotated[int, Query(description="Máximo de resultados (1 a 20).")] = (
        DEFAULT_SEARCH_LIMIT
    ),
) -> RegionListOut:
    """Búsqueda tolerante a acentos y errores de escritura."""
    regions = await SearchRegions(repository).execute(q, limit)
    return RegionListOut(items=[RegionOut.from_domain(r) for r in regions])


@router.get("/at", response_model=RegionOut, summary="Región en un punto")
async def region_at_point(
    repository: Repository,
    lon: Annotated[float, Query(description="Longitud en grados.")],
    lat: Annotated[float, Query(description="Latitud en grados.")],
    level: Annotated[
        LevelLiteral | None, Query(description="Nivel buscado; si se omite, el más específico.")
    ] = None,
) -> RegionOut:
    """Devuelve la región que contiene el punto."""
    region = await FindRegionAtPoint(repository).execute(
        lon, lat, RegionLevel(level) if level else None
    )
    return RegionOut.from_domain(region)


@router.get("/{region_id}", response_model=RegionDetailOut, summary="Detalle de una región")
async def get_region(
    repository: Repository, region_id: Annotated[int, Path(description="Id de la región.")]
) -> RegionDetailOut:
    """Detalle con ancestros, para las migas de pan."""
    detail = await GetRegion(repository).execute(region_id)
    return RegionDetailOut.from_detail(detail)


@router.get("/{region_id}/children", response_model=RegionPageOut, summary="Hijas de una región")
async def list_children(
    repository: Repository,
    region_id: Annotated[int, Path(description="Id de la región padre.")],
    cursor: Cursor = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
) -> RegionPageOut:
    """Hijas directas en orden alfabético (filtros encadenados)."""
    page = await ListChildren(repository).execute(region_id, cursor, limit)
    return RegionPageOut.from_page(page)
