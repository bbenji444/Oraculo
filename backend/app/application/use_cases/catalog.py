"""Edición del catálogo de subdivisiones (categorías) desde la pantalla (02/11/2026).

Benji pidió poder ver y editar todas las subdivisiones de la FGR, no solo las
que aparecen en una búsqueda. ``EditCategory`` aplica los cambios con las
reglas de ``CategoryChanges``, revisa que el nombre no choque y deja el
cambio en la bitácora (CLAUDE.md §8).

Las palabras clave del tema general de cada subdivisión se editan como las de
cualquier concepto (``UpdateConcept``), porque son un concepto.

No hace: no reclasifica las notas ya clasificadas; lo editado vale para las
siguientes.
"""

from app.application.audit import Actor, AuditEntry
from app.application.ports.categories import CategoryCatalogPort
from app.domain.categories import Category, CategoryChanges
from app.domain.errors import CategoryNotFoundError

CATEGORY_UPDATED = "category.updated"


def _snapshot(category: Category) -> dict[str, object]:
    return {
        "name": category.name,
        "description": category.description,
        "color": category.color,
        "is_active": category.is_active,
    }


class EditCategory:
    """Edita una subdivisión y registra el cambio."""

    def __init__(self, store: CategoryCatalogPort) -> None:
        """Recibe el catálogo.

        Args:
            store: Acceso a las categorías.
        """
        self._store = store

    async def execute(self, category_id: int, changes: CategoryChanges, actor: Actor) -> Category:
        """Aplica los cambios; si en realidad nada cambia, no escribe nada.

        Args:
            category_id: La subdivisión.
            changes: Lo que cambia.
            actor: Quién edita.

        Returns:
            La subdivisión como quedó.

        Raises:
            CategoryNotFoundError: Si no existe.
            CategoryValidationError: Si el resultado no cumple las reglas.
            CategoryNameTakenError: Si el nombre ya lo usa otra subdivisión o
                el concepto de otro tema.
        """
        current = await self._store.get_category(category_id)
        if current is None:
            raise CategoryNotFoundError("No existe esa subdivisión.", {"id": category_id})
        updated = changes.apply_to(current)
        if updated == current:
            return current
        before, after = _snapshot(current), _snapshot(updated)
        changed = [field for field in after if after[field] != before[field]]
        audit = AuditEntry(
            actor, CATEGORY_UPDATED, {"before": before, "after": after, "changed": changed}
        )
        return await self._store.update_category(updated, audit)
