"""Leer búsquedas para la API: detalle e historial (especificación §13).

No hace: no corre ni modifica búsquedas.
"""

from uuid import UUID

from app.application.pagination import Page, TimeCursor, decode_time_cursor, encode_time_cursor
from app.application.ports.search_reads import SearchDetail, SearchReaderPort
from app.application.use_cases.run_search import SearchNotFoundError
from app.domain.errors import InvalidRequestError

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
