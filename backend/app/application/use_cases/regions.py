"""Casos de uso de consulta del catálogo de regiones (endpoints ``/regions``).

Reglas que viven aquí y no en el router ni en SQL:
- Límites de página y de búsqueda.
- La búsqueda se normaliza con la misma función del cargador (conserva la Ñ)
  y exige al menos 2 letras, para no devolver medio país con "a".
- Las coordenadas se validan antes de consultar.
- Una región inexistente es un error de dominio con mensaje en español.

No hace: no sabe de HTTP ni de SQL.
"""

from app.application.pagination import NameCursor, Page, decode_cursor, encode_cursor
from app.application.ports.regions import RegionRepositoryPort
from app.domain.errors import InvalidRequestError, RegionNotFoundError
from app.domain.names import normalize_name
from app.domain.region import GeoPoint, Region, RegionDetail, RegionLevel

# Límite por página: 32 estados caben en una; los 570 municipios de Oaxaca,
# en tres. Más de 200 no hace falta para filtros encadenados.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
# Búsqueda: con 2 letras ya hay sugerencias útiles ("iz"); el autocompletado
# muestra 10 y nunca más de 20 (especificación §17 F1, plan aprobado).
MIN_SEARCH_LENGTH = 2
DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 20
_MAX_LONGITUDE = 180.0
_MAX_LATITUDE = 90.0


def _check_limit(limit: int, maximum: int) -> None:
    if not 1 <= limit <= maximum:
        raise InvalidRequestError(
            f"El límite debe estar entre 1 y {maximum}.", {"limit": limit, "max": maximum}
        )


def _paginate(rows: list[Region], limit: int) -> Page[Region]:
    """Arma la página: se pidió uno de más para saber si hay siguiente."""
    items = rows[:limit]
    has_more = len(rows) > limit
    next_cursor = (
        encode_cursor(NameCursor(items[-1].name_norm, items[-1].id)) if has_more and items else None
    )
    return Page(tuple(items), next_cursor)


def _cursor(token: str | None) -> NameCursor | None:
    return decode_cursor(token) if token else None


class ListRegions:
    """Lista las regiones de un nivel en orden alfabético, por páginas."""

    def __init__(self, repository: RegionRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso al catálogo.
        """
        self._repository = repository

    async def execute(
        self, level: RegionLevel, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
    ) -> Page[Region]:
        """Devuelve una página.

        Args:
            level: Nivel a listar.
            cursor: Cursor de la página anterior, o ``None`` para la primera.
            limit: Tamaño de página (1 a 200).

        Returns:
            La página con su cursor siguiente.

        Raises:
            InvalidRequestError: Si el límite o el cursor no son válidos.
        """
        _check_limit(limit, MAX_PAGE_SIZE)
        rows = await self._repository.list_by_level(level, _cursor(cursor), limit + 1)
        return _paginate(rows, limit)


class GetRegion:
    """Detalle de una región con sus ancestros (migas de pan)."""

    def __init__(self, repository: RegionRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso al catálogo.
        """
        self._repository = repository

    async def execute(self, region_id: int) -> RegionDetail:
        """Busca la región y sus ancestros.

        Args:
            region_id: Identificador.

        Returns:
            La región con sus ancestros, del más general al más cercano.

        Raises:
            RegionNotFoundError: Si no existe.
        """
        region = await self._repository.get(region_id)
        if region is None:
            raise RegionNotFoundError("No existe esa región.", {"id": region_id})
        ancestors = await self._repository.ancestors(region_id)
        return RegionDetail(region, tuple(ancestors))


class ListChildren:
    """Hijas de una región (para los filtros encadenados Estado → Municipio → Localidad)."""

    def __init__(self, repository: RegionRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso al catálogo.
        """
        self._repository = repository

    async def execute(
        self, region_id: int, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
    ) -> Page[Region]:
        """Devuelve una página de hijas.

        Args:
            region_id: Región padre.
            cursor: Cursor de la página anterior.
            limit: Tamaño de página (1 a 200).

        Returns:
            La página con su cursor siguiente.

        Raises:
            RegionNotFoundError: Si la región padre no existe.
            InvalidRequestError: Si el límite o el cursor no son válidos.
        """
        _check_limit(limit, MAX_PAGE_SIZE)
        if await self._repository.get(region_id) is None:
            raise RegionNotFoundError("No existe esa región.", {"id": region_id})
        rows = await self._repository.list_children(region_id, _cursor(cursor), limit + 1)
        return _paginate(rows, limit)


class SearchRegions:
    """Búsqueda por nombre o alias, tolerante a acentos y errores ("izta" → Iztapalapa)."""

    def __init__(self, repository: RegionRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso al catálogo.
        """
        self._repository = repository

    async def execute(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[Region]:
        """Busca regiones.

        Args:
            query: Texto tal como lo escribió el usuario.
            limit: Máximo de resultados (1 a 20).

        Returns:
            Las mejores coincidencias.

        Raises:
            InvalidRequestError: Si el texto tiene menos de 2 letras o el
                límite no es válido.

        Example:
            >>> await SearchRegions(repo).execute("izta")
            [Region(name='Iztapalapa', ...), Region(name='Iztacalco', ...)]
        """
        _check_limit(limit, MAX_SEARCH_LIMIT)
        query_norm = normalize_name(query)
        if len(query_norm) < MIN_SEARCH_LENGTH:
            raise InvalidRequestError(
                f"Escribe al menos {MIN_SEARCH_LENGTH} letras para buscar.", {"q": query}
            )
        return await self._repository.search(query_norm, limit)


class FindRegionAtPoint:
    """Región que contiene un punto del mapa."""

    def __init__(self, repository: RegionRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso al catálogo.
        """
        self._repository = repository

    async def execute(self, lon: float, lat: float, level: RegionLevel | None = None) -> Region:
        """Ubica el punto.

        Args:
            lon: Longitud en grados.
            lat: Latitud en grados.
            level: Nivel buscado; ``None`` para la región más específica.

        Returns:
            La región que contiene el punto.

        Raises:
            InvalidRequestError: Si las coordenadas están fuera de rango.
            RegionNotFoundError: Si ninguna región contiene el punto (por
                ejemplo, en el mar).
        """
        if not (
            -_MAX_LONGITUDE <= lon <= _MAX_LONGITUDE and -_MAX_LATITUDE <= lat <= _MAX_LATITUDE
        ):
            raise InvalidRequestError(
                "Las coordenadas están fuera de rango (longitud ±180, latitud ±90).",
                {"lon": lon, "lat": lat},
            )
        region = await self._repository.find_at_point(GeoPoint(lon, lat), level)
        if region is None:
            raise RegionNotFoundError(
                "No hay ninguna región en ese punto.",
                {"lon": lon, "lat": lat, "level": level.value if level else None},
            )
        return region
