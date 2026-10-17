"""Leer búsquedas para la API: detalle, historial, notas y detalle de nota (§13).

No hace: no corre ni modifica búsquedas.
"""

from dataclasses import dataclass
from uuid import UUID

from app.application.pagination import Page, TimeCursor, decode_time_cursor, encode_time_cursor
from app.application.ports.search_reads import (
    ArticleDetail,
    ArticleFilters,
    ArticleItem,
    ArticleReaderPort,
    RegionPoint,
    SearchDetail,
    SearchReaderPort,
)
from app.application.use_cases.run_search import SearchNotFoundError
from app.domain.aggregates import AggregateLevel, aggregate
from app.domain.errors import InvalidRequestError, NotFoundError
from app.domain.geocoding import Precision

# Precisiones válidas para filtrar (``unknown`` = sin ubicación).
PRECISIONS = frozenset(p.value for p in Precision)
# Búsquedas por página del historial: una pantalla cómoda.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def check_limit(limit: int, maximum: int = MAX_PAGE_SIZE) -> None:
    """Rechaza tamaños de página fuera de rango.

    Args:
        limit: Tamaño pedido.
        maximum: Máximo permitido.

    Raises:
        InvalidRequestError: Si no está entre 1 y ``maximum``.
    """
    if not 1 <= limit <= maximum:
        raise InvalidRequestError(f"El límite debe estar entre 1 y {maximum}.", {"limit": limit})


class GetSearch:
    """Una búsqueda con su estado y avance (la pantalla la consulta mientras corre)."""

    def __init__(self, reader: SearchReaderPort) -> None:
        """Recibe el lector.

        Args:
            reader: Lecturas de búsquedas.
        """
        self._reader = reader

    async def execute(self, search_id: UUID) -> SearchDetail:
        """Devuelve la búsqueda.

        Args:
            search_id: Id.

        Returns:
            La búsqueda.

        Raises:
            SearchNotFoundError: Si no existe.
        """
        detail = await self._reader.search_detail(search_id)
        if detail is None:
            raise SearchNotFoundError("No existe esa búsqueda.", {"id": str(search_id)})
        return detail


class ListSearches:
    """Historial de búsquedas de una persona, por páginas."""

    def __init__(self, reader: SearchReaderPort) -> None:
        """Recibe el lector.

        Args:
            reader: Lecturas de búsquedas.
        """
        self._reader = reader

    async def execute(
        self, user_id: str, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
    ) -> Page[SearchDetail]:
        """Devuelve una página, de la más reciente a la más vieja.

        Args:
            user_id: Quién las pidió.
            cursor: Cursor de la página anterior.
            limit: Tamaño de página (1 a 100).

        Returns:
            La página con su cursor siguiente.

        Raises:
            InvalidRequestError: Si el límite o el cursor no son válidos.
        """
        check_limit(limit)
        after = decode_time_cursor(cursor) if cursor else None
        rows = await self._reader.history(user_id, after, limit + 1)
        items = rows[:limit]
        next_cursor = (
            encode_time_cursor(TimeCursor(items[-1].created_at, str(items[-1].search_id)))
            if len(rows) > limit and items
            else None
        )
        return Page(tuple(items), next_cursor)


# Notas por página: una lista cómoda; el mapa usa los conteos (aggregates).
DEFAULT_ARTICLE_PAGE_SIZE = 50
MAX_ARTICLE_PAGE_SIZE = 200


class ArticleNotFoundError(NotFoundError):
    """La nota pedida no existe."""

    code = "article_not_found"


class ListSearchArticles:
    """Notas de una búsqueda con filtros, por páginas."""

    def __init__(self, searches: SearchReaderPort, articles: ArticleReaderPort) -> None:
        """Recibe los lectores.

        Args:
            searches: Lecturas de búsquedas (para el 404).
            articles: Lecturas de notas.
        """
        self._searches = searches
        self._articles = articles

    async def execute(
        self,
        search_id: UUID,
        filters: ArticleFilters,
        cursor: str | None = None,
        limit: int = DEFAULT_ARTICLE_PAGE_SIZE,
    ) -> Page[ArticleItem]:
        """Devuelve una página, de la nota más reciente a la más vieja.

        Args:
            search_id: Búsqueda.
            filters: Filtros.
            cursor: Cursor de la página anterior.
            limit: Tamaño de página (1 a 200).

        Returns:
            La página con su cursor siguiente.

        Raises:
            SearchNotFoundError: Si la búsqueda no existe.
            InvalidRequestError: Si el límite, la precisión o el cursor no
                son válidos.
        """
        check_limit(limit, MAX_ARTICLE_PAGE_SIZE)
        unknown = filters.precisions - PRECISIONS
        if unknown:
            raise InvalidRequestError(
                f"Precisión desconocida: {', '.join(sorted(unknown))}.",
                {"validas": sorted(PRECISIONS)},
            )
        await GetSearch(self._searches).execute(search_id)
        after = decode_time_cursor(cursor) if cursor else None
        rows = await self._articles.search_articles(search_id, filters, after, limit + 1)
        items = rows[:limit]
        next_cursor = (
            encode_time_cursor(TimeCursor(items[-1].published_at, str(items[-1].article_id)))
            if len(rows) > limit and items
            else None
        )
        return Page(tuple(items), next_cursor)


class GetArticle:
    """Una nota con todas sus menciones de lugar y juicios de la IA."""

    def __init__(self, articles: ArticleReaderPort) -> None:
        """Recibe el lector.

        Args:
            articles: Lecturas de notas.
        """
        self._articles = articles

    async def execute(self, article_id: int) -> ArticleDetail:
        """Devuelve la nota.

        Args:
            article_id: Id.

        Returns:
            La nota.

        Raises:
            ArticleNotFoundError: Si no existe.
        """
        detail = await self._articles.article_detail(article_id)
        if detail is None:
            raise ArticleNotFoundError("No existe esa nota.", {"id": article_id})
        return detail


@dataclass(frozen=True, slots=True)
class AggregateItem:
    """Una región con su conteo.

    Attributes:
        region: Región (nombre y centro).
        count: Notas que caen ahí.
    """

    region: RegionPoint
    count: int


@dataclass(frozen=True, slots=True)
class AggregatesView:
    """El mapa de calor de una búsqueda.

    Attributes:
        level: Nivel pedido.
        items: Regiones con notas, de la que más tiene a la que menos.
        coarser: Notas ubicadas con menos precisión que el nivel.
        abroad: Notas de otro país.
        unlocated: Notas sin ubicación.
        total: Todas las notas contadas.
    """

    level: AggregateLevel
    items: tuple[AggregateItem, ...]
    coarser: int
    abroad: int
    unlocated: int
    total: int


class GetAggregates:
    """Conteo de notas por región para el mapa de calor."""

    def __init__(self, searches: SearchReaderPort, articles: ArticleReaderPort) -> None:
        """Recibe los lectores.

        Args:
            searches: Lecturas de búsquedas (para el 404).
            articles: Lecturas de notas.
        """
        self._searches = searches
        self._articles = articles

    async def execute(
        self, search_id: UUID, level: AggregateLevel, filters: ArticleFilters
    ) -> AggregatesView:
        """Agrupa las notas de la búsqueda.

        Args:
            search_id: Búsqueda.
            level: País, estado o municipio.
            filters: Los mismos filtros de la lista de notas.

        Returns:
            Conteos por región, con nombre y centro.

        Raises:
            SearchNotFoundError: Si la búsqueda no existe.
        """
        await GetSearch(self._searches).execute(search_id)
        result = aggregate(await self._articles.note_locations(search_id, filters), level)
        regions = {r.code: r for r in await self._articles.regions_by_code(sorted(result.counts))}
        items = sorted(
            (
                AggregateItem(regions[code], count)
                for code, count in result.counts.items()
                if code in regions
            ),
            key=lambda i: (-i.count, i.region.name),
        )
        return AggregatesView(
            level, tuple(items), result.coarser, result.abroad, result.unlocated, result.total
        )
