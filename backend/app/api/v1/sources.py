"""Fuentes que el analista puede encender o apagar en la búsqueda manual (F12.2).

``GET /sources`` alimenta los switches del panel de búsqueda: nombre, si
cuesta créditos, si está configurada y si va encendida por defecto. La
elección se manda luego en ``providers`` de ``/searches`` (ADR-0027).

No hace: no decide qué fuentes existen (``app.domain.sources``) ni cuáles
están configuradas (``PlanSearch.source_options``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.errors import ERROR_RESPONSES
from app.api.v1.searches import get_search_planner
from app.application.use_cases.plan_search import PlanSearch, SourceOption

router = APIRouter(prefix="/sources", tags=["fuentes"], responses=ERROR_RESPONSES)

Planner = Annotated[PlanSearch, Depends(get_search_planner)]


class SourceOut(BaseModel):
    """Un switch de fuente."""

    id: str = Field(examples=["google_news_rss"], description="Valor para ``providers``.")
    label: str = Field(examples=["Google News"])
    paid: bool = Field(description="Si gasta créditos (SearchApi) o es gratis.")
    configured: bool = Field(
        description="Si tiene lo necesario para consultar; si no, el switch se deshabilita."
    )
    default_on: bool = Field(description="Si va encendida al abrir la búsqueda.")

    @classmethod
    def from_option(cls, option: SourceOption) -> "SourceOut":
        """Convierte la opción del caso de uso.

        Args:
            option: Fuente con su estado.

        Returns:
            El esquema.
        """
        return cls(
            id=option.source.provider.value,
            label=option.source.label,
            paid=option.source.paid,
            configured=option.configured,
            default_on=option.default_on,
        )


class SourceListOut(BaseModel):
    """Las fuentes, en el orden en que se muestran."""

    items: list[SourceOut]


@router.get("", response_model=SourceListOut, summary="Fuentes de la búsqueda manual")
async def list_sources(planner: Planner) -> SourceListOut:
    """Switches de fuentes: cuáles hay, cuáles cuestan y cuáles están encendidas."""
    return SourceListOut(items=[SourceOut.from_option(o) for o in planner.source_options()])
