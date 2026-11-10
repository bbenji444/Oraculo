"""Edición del catálogo de subdivisiones (categorías) desde la pantalla (02/11/2026).

Benji pidió poder ver y editar todas las subdivisiones de la FGR, no solo las
que aparecen en una búsqueda. ``EditCategory`` aplica los cambios con las
reglas de ``CategoryChanges``, revisa que el nombre no choque y deja el
cambio en la bitácora (CLAUDE.md §8).

Las palabras clave del tema general de cada subdivisión se editan como las de
cualquier concepto (``UpdateConcept``), porque son un concepto.

Desde el 09/11/2026 las subdivisiones se agregan (``CreateCategory``, con su
tema general) y se borran (``DeleteCategory``: sus notas pasan a «Otros»),
porque Benji pidió que fueran editables al 100%.

No hace: no reclasifica las notas ya clasificadas; lo editado vale para las
siguientes.
"""

from app.application.audit import Actor, AuditEntry
from app.application.ports.categories import CategoryCatalogPort
from app.domain.categories import Category, CategoryChanges
from app.domain.concept import ConceptDraft
from app.domain.errors import CategoryNotFoundError, CategoryValidationError

CATEGORY_UPDATED = "category.updated"
CATEGORY_CREATED = "category.created"
CATEGORY_DELETED = "category.deleted"
# Plantilla vacía para validar una subdivisión nueva con las mismas reglas que
# una edición (``CategoryChanges.apply_to``).
_BLANK = Category(0, "", "")


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


class CreateCategory:
    """Agrega una subdivisión con su tema general y registra el alta."""

    def __init__(self, store: CategoryCatalogPort) -> None:
        """Recibe el catálogo.

        Args:
            store: Acceso a las categorías.
        """
        self._store = store

    async def execute(
        self,
        changes: CategoryChanges,
        keywords: tuple[str, ...],
        exclude_terms: tuple[str, ...],
        actor: Actor,
    ) -> Category:
        """Valida y guarda la subdivisión nueva.

        La IA la usa al clasificar las notas que lleguen después; las ya
        clasificadas no cambian.

        Args:
            changes: Nombre, descripción (lo que lee la IA), color y si está prendida.
            keywords: Palabras clave de su tema general (al menos una).
            exclude_terms: Términos que descartan una nota del tema general.
            actor: Quién la crea.

        Returns:
            La subdivisión guardada.

        Raises:
            CategoryValidationError: Sin nombre, sin color o con datos inválidos.
            ConceptValidationError: Si las palabras clave no cumplen sus reglas.
            CategoryNameTakenError: Si el nombre ya lo usa otra subdivisión o concepto.
        """
        category = changes.apply_to(_BLANK)
        if category.color is None:
            raise CategoryValidationError(
                "La subdivisión no cumple sus reglas.",
                {"problemas": [{"campo": "color", "mensaje": "Elige un color."}]},
            )
        topic = ConceptDraft.validated(
            name=category.name,
            description="",
            keywords=keywords,
            exclude_terms=exclude_terms,
            color=category.color,
            is_active=category.is_active,
        )
        audit = AuditEntry(
            actor,
            CATEGORY_CREATED,
            {"after": _snapshot(category), "keywords": list(topic.keywords)},
        )
        return await self._store.create_category(category, topic, actor.user_id, audit)


class DeleteCategory:
    """Borra una subdivisión; sus notas pasan a «Otros»."""

    def __init__(self, store: CategoryCatalogPort) -> None:
        """Recibe el catálogo.

        Args:
            store: Acceso a las categorías.
        """
        self._store = store

    async def execute(self, category_id: int, actor: Actor) -> int:
        """Borra la subdivisión y registra la baja.

        Args:
            category_id: La subdivisión.
            actor: Quién la borra.

        Returns:
            Cuántas notas pasaron a «Otros».

        Raises:
            CategoryNotFoundError: Si no existe.
            CategoryValidationError: Si es «Otros» (toda nota necesita a dónde ir).
        """
        current = await self._store.get_category(category_id)
        if current is None:
            raise CategoryNotFoundError("No existe esa subdivisión.", {"id": category_id})
        if current.is_other:
            raise CategoryValidationError(
                "«Otros» no se borra: es a donde va lo que no encaja.",
                {"problemas": [{"campo": "id", "mensaje": "«Otros» no se borra."}]},
            )
        audit = AuditEntry(actor, CATEGORY_DELETED, {"before": _snapshot(current)})
        return await self._store.delete_category(current, audit)
