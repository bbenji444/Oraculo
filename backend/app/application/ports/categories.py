"""Puerto del catálogo de categorías y de la categoría de cada nota (F12.4, ADR-0029).

``ClassifyArticles`` lo usa para leer el catálogo, saber qué notas faltan
por clasificar (o se clasificaron con otra versión del prompt) y guardar lo
que eligió la IA. La implementación vive en ``adapters/persistence``.

``CategoryCatalogPort`` (02/11/2026) es lo que usa el editor de
subdivisiones: leer todo el catálogo y guardar una edición. Desde el
09/11/2026 también agregar y borrar subdivisiones. Van separados
para que clasificar no dependa de editar.

No hace: no decide la categoría (eso es ``app.domain.categories``).
"""

from collections.abc import Sequence
from typing import Protocol

from app.application.audit import AuditEntry
from app.application.ports.llm import ClassificationNote
from app.domain.categories import Category, CategoryChoice
from app.domain.concept import ConceptDraft


class CategoryCatalogPort(Protocol):
    """El catálogo de subdivisiones, para verlo y editarlo."""

    async def active_categories(self) -> list[Category]:
        """El catálogo activo, en su orden, con su tema general.

        Returns:
            Las categorías activas (incluida «Otros»).
        """
        ...

    async def all_categories(self) -> list[Category]:
        """Todo el catálogo, también las apagadas, con su tema general (editor).

        Returns:
            Las categorías en su orden.
        """
        ...

    async def get_category(self, category_id: int) -> Category | None:
        """Una categoría por id.

        Args:
            category_id: Id.

        Returns:
            La categoría, o ``None`` si no existe.
        """
        ...

    async def update_category(self, category: Category, audit: AuditEntry) -> Category:
        """Guarda la categoría editada y deja el cambio en la bitácora.

        Su tema general toma el mismo nombre y se prende o apaga con ella.

        Args:
            category: Como quedó (``CategoryChanges.apply_to``).
            audit: Registro para la bitácora.

        Returns:
            La categoría guardada.

        Raises:
            CategoryNameTakenError: Si otra categoría o concepto ya usa el nombre.
        """
        ...

    async def create_category(
        self, category: Category, topic: ConceptDraft, actor_id: str, audit: AuditEntry
    ) -> Category:
        """Agrega una subdivisión con su tema general, antes de «Otros».

        Args:
            category: La subdivisión nueva (su id se ignora).
            topic: Su tema general: mismo nombre, palabras clave y color.
            actor_id: Quién la crea (firma del tema general).
            audit: Registro para la bitácora.

        Returns:
            La subdivisión guardada, con su id y el de su tema general.

        Raises:
            CategoryNameTakenError: Si otra categoría o concepto ya usa el nombre.
        """
        ...

    async def delete_category(self, category: Category, audit: AuditEntry) -> int:
        """Borra una subdivisión: sus notas pasan a «Otros» y su tema general se retira.

        El tema general se borra de forma lógica (``deleted_at``): las
        búsquedas pasadas lo conservan con su nombre.

        Args:
            category: La subdivisión (nunca «Otros»).
            audit: Registro para la bitácora.

        Returns:
            Cuántas notas pasaron a «Otros».
        """
        ...


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
