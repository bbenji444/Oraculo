"""Catálogo de categorías de noticias (``GET /categories``, F12.4, ADR-0029).

La lista que la IA usa para clasificar cada nota por delito, en su orden.
Sirve para leyendas, filtros y el reporte.

Desde el 02/11/2026 también se editan (``PATCH /categories/{id}``): son las
subdivisiones de la FGR y cada una tiene su tema general para buscar sin la
FGR (``topic_concept_id``), cuyas palabras clave se editan en ``/concepts``.
Desde el 09/11/2026 se agregan (``POST``, con su tema general) y se borran
(``DELETE``: sus notas pasan a «Otros»).

No hace: no clasifica (eso pasa al cerrar cada búsqueda).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.concepts import get_actor
from app.application.audit import Actor
from app.application.ports.categories import CategoryCatalogPort
from app.application.use_cases.catalog import CreateCategory, DeleteCategory, EditCategory
from app.domain.categories import Category, CategoryChanges

router = APIRouter(prefix="/categories", tags=["categorías"], responses=ERROR_RESPONSES)


def get_category_store(request: Request) -> CategoryCatalogPort:
    """Catálogo creado al arrancar la aplicación.

    Args:
        request: Petición actual.

    Returns:
        El repositorio compartido.
    """
    store: CategoryCatalogPort = request.app.state.category_store
    return store


Store = Annotated[CategoryCatalogPort, Depends(get_category_store)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


class CategoryItemOut(BaseModel):
    """Una categoría del catálogo."""

    id: int
    name: str = Field(examples=["Huachicol y delitos contra hidrocarburos"])
    description: str = Field(description="Qué entra en ella (es lo que lee la IA).")
    is_other: bool = Field(description="Si es la de respaldo («Otros»).")
    color: str | None = None
    symbol: str | None = None
    is_active: bool = Field(default=True, description="Si la IA la usa al clasificar.")
    topic_concept_id: int | None = Field(
        default=None,
        description="Su tema general para buscar sin la FGR (``/concepts``), si tiene.",
    )

    @classmethod
    def from_domain(cls, category: Category) -> "CategoryItemOut":
        """Convierte una ``Category`` del dominio.

        Args:
            category: La categoría.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            id=category.category_id,
            name=category.name,
            description=category.description,
            is_other=category.is_other,
            color=category.color,
            symbol=category.symbol,
            is_active=category.is_active,
            topic_concept_id=category.topic_concept_id,
        )


class CategoryListOut(BaseModel):
    """El catálogo, en su orden."""

    items: list[CategoryItemOut]


class CategoryPatchIn(BaseModel):
    """Lo que cambia de una subdivisión; lo que no se manda queda igual."""

    name: str | None = Field(default=None, examples=["Homicidio"])
    description: str | None = Field(
        default=None, description="Lo que debe entender la IA por ella."
    )
    color: str | None = Field(default=None, examples=["#FF4D6D"])
    is_active: bool | None = None

    def to_changes(self) -> CategoryChanges:
        """Los cambios para el caso de uso.

        Returns:
            ``CategoryChanges`` con los campos mandados.
        """
        return CategoryChanges(self.name, self.description, self.color, self.is_active)


@router.get("", response_model=CategoryListOut, summary="Categorías de noticias")
async def list_categories(
    store: Store,
    include_inactive: Annotated[
        bool, Query(description="true: también las apagadas (el editor de subdivisiones).")
    ] = False,
) -> CategoryListOut:
    """Las categorías con que se clasifica cada nota por delito, con «Otros» al final."""
    categories = await (store.all_categories() if include_inactive else store.active_categories())
    return CategoryListOut(items=[CategoryItemOut.from_domain(c) for c in categories])


@router.patch(
    "/{category_id}",
    response_model=CategoryItemOut,
    summary="Editar una subdivisión",
    responses=error_responses(404, 409),
)
async def edit_category(
    category_id: int, body: CategoryPatchIn, store: Store, actor: CurrentActor
) -> CategoryItemOut:
    """Cambia nombre, descripción, color o si está prendida; queda en la bitácora."""
    category = await EditCategory(store).execute(category_id, body.to_changes(), actor)
    return CategoryItemOut.from_domain(category)


class CategoryCreateIn(BaseModel):
    """Una subdivisión nueva con su tema general."""

    name: str = Field(examples=["Feminicidio"])
    description: str = Field(
        default="", description="Qué entra en ella; es lo que lee la IA al clasificar."
    )
    color: str = Field(examples=["#FF4D6D"])
    is_active: bool = True
    keywords: list[str] = Field(
        description="Palabras clave de su tema general (al menos una).",
        examples=[["feminicidio", "feminicidios"]],
    )
    exclude_terms: list[str] = Field(default_factory=list)


class CategoryDeleteOut(BaseModel):
    """Cómo quedó el borrado."""

    notes_moved_to_other: int = Field(description="Notas que pasaron a «Otros».")


@router.post(
    "",
    response_model=CategoryItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar una subdivisión",
    responses=error_responses(409, 422),
)
async def create_category(
    body: CategoryCreateIn, store: Store, actor: CurrentActor
) -> CategoryItemOut:
    """Agrega una subdivisión antes de «Otros», con su tema general; queda en la bitácora.

    La IA la usa con las notas que se clasifiquen después.
    """
    category = await CreateCategory(store).execute(
        CategoryChanges(body.name, body.description, body.color, body.is_active),
        tuple(body.keywords),
        tuple(body.exclude_terms),
        actor,
    )
    return CategoryItemOut.from_domain(category)


@router.delete(
    "/{category_id}",
    response_model=CategoryDeleteOut,
    summary="Borrar una subdivisión",
    responses=error_responses(404, 422),
)
async def delete_category(category_id: int, store: Store, actor: CurrentActor) -> CategoryDeleteOut:
    """Borra una subdivisión: sus notas pasan a «Otros» y su tema general se retira.

    «Otros» no se borra (``422 invalid_category``).
    """
    moved = await DeleteCategory(store).execute(category_id, actor)
    return CategoryDeleteOut(notes_moved_to_other=moved)
