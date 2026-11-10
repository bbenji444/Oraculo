"""Editor de subdivisiones (editar, agregar y borrar), con un catálogo en memoria."""

import pytest

from app.application.audit import Actor, AuditEntry
from app.application.use_cases.catalog import (
    CATEGORY_CREATED,
    CATEGORY_DELETED,
    CATEGORY_UPDATED,
    CreateCategory,
    DeleteCategory,
    EditCategory,
)
from app.domain.categories import Category, CategoryChanges
from app.domain.concept import ConceptDraft
from app.domain.errors import (
    CategoryNotFoundError,
    CategoryValidationError,
    ConceptValidationError,
)

pytestmark = pytest.mark.anyio

BENJI = Actor("benji")
HOMICIDIO = Category(5, "Homicidio", "Asesinatos", color="#FF4D6D", topic_concept_id=21)
OTROS = Category(14, "Otros", "Lo que no encaja", is_other=True)


class FakeCatalog:
    """Implementa ``CategoryCatalogPort`` en memoria."""

    def __init__(self, *categories: Category) -> None:
        self.categories = {c.category_id: c for c in categories}
        self.audit: list[AuditEntry] = []
        self.topics: list[tuple[ConceptDraft, str]] = []

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

    async def create_category(
        self, category: Category, topic: ConceptDraft, actor_id: str, audit: AuditEntry
    ) -> Category:
        new_id = max(self.categories, default=0) + 1
        saved = Category(
            new_id,
            category.name,
            category.description,
            color=category.color,
            is_active=category.is_active,
            topic_concept_id=100 + new_id,
        )
        self.categories[new_id] = saved
        self.topics.append((topic, actor_id))
        self.audit.append(audit)
        return saved

    async def delete_category(self, category: Category, audit: AuditEntry) -> int:
        del self.categories[category.category_id]
        self.audit.append(audit)
        return 7


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


async def test_agrega_una_subdivision_con_su_tema_general() -> None:
    catalog = FakeCatalog(HOMICIDIO, OTROS)

    created = await CreateCategory(catalog).execute(
        CategoryChanges("  Feminicidio ", "Asesinato de mujeres por razón de género", "#ff4d6d"),
        ("feminicidio", "feminicidios"),
        (),
        BENJI,
    )

    assert (created.name, created.color, created.topic_concept_id) == (
        "Feminicidio",
        "#FF4D6D",
        100 + created.category_id,
    )
    [(topic, actor_id)] = catalog.topics
    assert (topic.name, topic.keywords, topic.color, actor_id) == (
        "Feminicidio",
        ("feminicidio", "feminicidios"),
        "#FF4D6D",
        "benji",
    )
    [entry] = catalog.audit
    assert (entry.action, entry.payload["keywords"]) == (
        CATEGORY_CREATED,
        ["feminicidio", "feminicidios"],
    )


async def test_una_subdivision_nueva_necesita_nombre_color_y_palabras() -> None:
    catalog = FakeCatalog(OTROS)
    create = CreateCategory(catalog)

    with pytest.raises(CategoryValidationError):
        await create.execute(CategoryChanges("   ", "", "#FF4D6D"), ("x",), (), BENJI)
    with pytest.raises(CategoryValidationError, match="regla"):
        await create.execute(CategoryChanges("Feminicidio", ""), ("feminicidio",), (), BENJI)
    with pytest.raises(ConceptValidationError):
        await create.execute(CategoryChanges("Feminicidio", "", "#FF4D6D"), (), (), BENJI)
    assert catalog.audit == []


async def test_borra_una_subdivision_y_sus_notas_van_a_otros() -> None:
    catalog = FakeCatalog(HOMICIDIO, OTROS)

    moved = await DeleteCategory(catalog).execute(5, BENJI)

    assert moved == 7
    assert 5 not in catalog.categories
    [entry] = catalog.audit
    assert entry.action == CATEGORY_DELETED
    assert entry.payload["before"] == {
        "name": "Homicidio",
        "description": "Asesinatos",
        "color": "#FF4D6D",
        "is_active": True,
    }


async def test_otros_no_se_borra_y_lo_que_no_existe_tampoco() -> None:
    catalog = FakeCatalog(HOMICIDIO, OTROS)

    with pytest.raises(CategoryValidationError, match="Otros"):
        await DeleteCategory(catalog).execute(14, BENJI)
    with pytest.raises(CategoryNotFoundError):
        await DeleteCategory(catalog).execute(99, BENJI)
    assert catalog.audit == []
