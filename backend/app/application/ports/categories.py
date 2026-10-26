"""Puerto del catálogo de categorías y de la categoría de cada nota (F12.4, ADR-0029).

``ClassifyArticles`` lo usa para leer el catálogo, saber qué notas faltan
por clasificar (o se clasificaron con otra versión del prompt) y guardar lo
que eligió la IA. La implementación vive en ``adapters/persistence``.

No hace: no decide la categoría (eso es ``app.domain.categories``).
"""

from collections.abc import Sequence
from typing import Protocol

from app.application.ports.llm import ClassificationNote
from app.domain.categories import Category, CategoryChoice


class CategoryStorePort(Protocol):
    """Catálogo y categoría de las notas."""

    async def active_categories(self) -> list[Category]:
        """El catálogo activo, en su orden.

        Returns:
            Las categorías activas (incluida «Otros»).
        """
        ...

    async def pending_notes(
        self, article_ids: Sequence[int], version: str
    ) -> list[ClassificationNote]:
        """De esas notas, las que no tienen categoría de esta versión del prompt.

        Args:
            article_ids: Notas candidatas.
            version: Versión vigente del prompt de clasificación.

        Returns:
            Título y resumen (o fragmento) de las que faltan.
        """
        ...

    async def pending_after(
        self, after_id: int, limit: int, version: str
    ) -> list[ClassificationNote]:
        """Notas sin categoría de esta versión, con id mayor que ``after_id`` (cursor).

        Args:
            after_id: Último id del lote anterior (0 al empezar).
            limit: Tamaño del lote.
            version: Versión vigente del prompt de clasificación.

        Returns:
            Las notas, en orden de id; vacío cuando ya no hay.
        """
        ...

    async def save(self, choices: Sequence[CategoryChoice], version: str) -> None:
        """Guarda la categoría de cada nota en una transacción.

        Args:
            choices: Categoría y etiqueta de cada nota.
            version: Versión del prompt que las clasificó.
        """
        ...
