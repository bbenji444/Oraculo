"""EditCategory: el editor de subdivisiones, con un catálogo en memoria."""

import pytest

from app.application.audit import Actor, AuditEntry
from app.application.use_cases.catalog import CATEGORY_UPDATED, EditCategory
from app.domain.categories import Category, CategoryChanges
from app.domain.errors import CategoryNotFoundError, CategoryValidationError

pytestmark = pytest.mark.anyio

BENJI = Actor("benji")
HOMICIDIO = Category(5, "Homicidio", "Asesinatos", color="#FF4D6D", topic_concept_id=21)


class FakeCatalog:
    """Implementa ``CategoryCatalogPort`` en memoria."""

    def __init__(self, *categories: Category) -> None:
        self.categories = {c.category_id: c for c in categories}
        self.audit: list[AuditEntry] = []

    async def active_categories(self) -> list[Category]:
        return [c for c in self.categories.values() if c.is_active]

    async def all_categories(self) -> list[Category]:
        return list(self.categories.values())

    async def get_category(self, category_id: int) -> Category | None:
        return self.categories.get(category_id)

    async def update_category(self, category: Category, audit: AuditEntry) -> Category:
        self.categories[category.category_id] = category
        self.audit.append(audit)
        return category


async def test_edita_y_deja_antes_y_despues_en_la_bitacora() -> None:
    catalog = FakeCatalog(HOMICIDIO)

    edited = await EditCategory(catalog).execute(
        5, CategoryChanges(name="Homicidio doloso", is_active=False), BENJI
    )

    assert (edited.name, edited.is_active, edited.topic_concept_id) == (
        "Homicidio doloso",
        False,
        21,
    )
    [entry] = catalog.audit
    assert entry.action == CATEGORY_UPDATED
    assert entry.payload["changed"] == ["name", "is_active"]
    assert entry.payload["before"] == {
        "name": "Homicidio",
        "description": "Asesinatos",
        "color": "#FF4D6D",
        "is_active": True,
    }


async def test_sin_cambios_reales_no_escribe() -> None:
    catalog = FakeCatalog(HOMICIDIO)

    same = await EditCategory(catalog).execute(
        5, CategoryChanges(name=" Homicidio ", color="#ff4d6d"), BENJI
    )

    assert same == HOMICIDIO
    assert catalog.audit == []


async def test_errores() -> None:
    use = EditCategory(FakeCatalog(HOMICIDIO))

    with pytest.raises(CategoryNotFoundError):
        await use.execute(99, CategoryChanges(name="X"), BENJI)
    with pytest.raises(CategoryValidationError):
        await use.execute(5, CategoryChanges(color="rojo"), BENJI)
