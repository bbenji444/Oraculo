"""Lecturas para revisar la relevancia de una búsqueda ya hecha (ADR-0114).

``make revisar-relevancia`` solo lee. Para que no pueda escribir nada y se
pruebe con dobles pequeños, aquí se piden únicamente las lecturas que usa.
Ya las implementan los repositorios de siempre: ``PostgresSearchStore``
(la copia de la búsqueda y su avance) y ``PostgresArticleStore`` (sus
notas con los juicios ya aplicados).

No hace: no escribe, no llama a la IA ni a los proveedores.
"""

from typing import Protocol
from uuid import UUID

from app.application.pagination import TimeCursor
from app.application.ports.search_reads import ArticleFilters, ArticleItem, SearchDetail
from app.application.ports.search_store import StoredSearch


class SearchCopyReaderPort(Protocol):
    """La búsqueda tal como se pidió (conceptos copiados) y su avance."""

    async def load(self, search_id: UUID) -> StoredSearch | None:
        """La búsqueda con sus conceptos copiados (texto, frases, términos obligatorios).

        Args:
            search_id: Búsqueda.

        Returns:
            La búsqueda, o ``None`` si no existe.
        """
        ...

    async def search_detail(self, search_id: UUID) -> SearchDetail | None:
        """Región, avance (``progress``) y costos de la búsqueda.

        Args:
            search_id: Búsqueda.

        Returns:
            El detalle, o ``None`` si no existe.
        """
        ...

    async def last_search_id(self) -> UUID | None:
        """La búsqueda más reciente.

        Returns:
            Su id, o ``None`` si no hay ninguna.
        """
        ...


class SearchArticlesReaderPort(Protocol):
    """Las notas de una búsqueda con sus juicios (relevancia final ya aplicada)."""

    async def search_articles(
        self, search_id: UUID, filters: ArticleFilters, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        """Una página de notas, de la más reciente a la más vieja.

        Args:
            search_id: Búsqueda.
            filters: Filtros (la revisión pide todas: relevantes o no, de
                cualquier región).
            after: Cursor de la página anterior.
            limit: Cuántas como máximo.

        Returns:
            Las notas de la página.
        """
        ...
