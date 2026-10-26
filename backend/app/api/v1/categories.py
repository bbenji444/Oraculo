"""Catálogo de categorías de noticias (``GET /categories``, F12.4, ADR-0029).

La lista que la IA usa para clasificar cada nota por delito, en su orden.
Sirve para leyendas, filtros y el reporte. Los colores y símbolos se definen
después con datos reales, así que hoy vienen en ``null``.

No hace: no clasifica (eso pasa al cerrar cada búsqueda) ni edita el catálogo.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.errors import ERROR_RESPONSES
from app.application.ports.categories import CategoryStorePort

router = APIRouter(prefix="/categories", tags=["categorías"], responses=ERROR_RESPONSES)


def get_category_store(request: Request) -> CategoryStorePort:
    """Catálogo creado al arrancar la aplicación.

    Args:
        request: Petición actual.

    Returns:
        El repositorio compartido.
    """
    store: CategoryStorePort = request.app.state.category_store
    return store


Store = Annotated[CategoryStorePort, Depends(get_category_store)]


class CategoryItemOut(BaseModel):
    """Una categoría del catálogo."""

    id: int
    name: str = Field(examples=["Huachicol y delitos contra hidrocarburos"])
    description: str = Field(description="Qué entra en ella (es lo que lee la IA).")
    is_other: bool = Field(description="Si es la de respaldo («Otros»).")
    color: str | None = None
    symbol: str | None = None


class CategoryListOut(BaseModel):
    """El catálogo activo, en su orden."""

    items: list[CategoryItemOut]


@router.get("", response_model=CategoryListOut, summary="Categorías de noticias")
async def list_categories(store: Store) -> CategoryListOut:
    """Las categorías con que se clasifica cada nota por delito, con «Otros» al final."""
    return CategoryListOut(
        items=[
            CategoryItemOut(
                id=c.category_id,
                name=c.name,
                description=c.description,
                is_other=c.is_other,
                color=c.color,
                symbol=c.symbol,
            )
            for c in await store.active_categories()
        ]
    )
