"""Esquemas de respuesta de ``/api/v1/regions``.

Traducen las entidades del dominio al JSON público. Nunca incluyen la
geometría completa: el mapa la obtiene de los PMTiles (especificación §14.2).
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.application.pagination import Page
from app.domain.region import Region, RegionDetail, RegionRef

LevelLiteral = Literal["country", "state", "municipality", "locality"]


class PointOut(BaseModel):
    """Punto representativo, siempre dentro de la región."""

    lon: float
    lat: float


class RegionOut(BaseModel):
    """Región del catálogo."""

    id: int
    level: LevelLiteral
    code: str = Field(description="Clave INEGI (09007) o ISO-A3 (COL).")
    name: str = Field(description="Nombre original, con acentos.")
    display_name: str = Field(description='Nombre para mostrar: "Alcaldía Iztapalapa".')
    display_prefix: str
    country_code: str
    parent_id: int | None
    point: PointOut
    bbox: tuple[float, float, float, float] = Field(
        description="[oeste, sur, este, norte] en grados, listo para fitBounds."
    )
    has_polygon: bool = Field(description="false en localidades que solo tienen punto.")
    aliases: list[str]

    @classmethod
    def from_domain(cls, region: Region) -> "RegionOut":
        """Convierte una ``Region`` del dominio.

        Args:
            region: Región del dominio.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            id=region.id,
            level=region.level.value,
            code=region.code,
            name=region.name,
            display_name=region.display_name,
            display_prefix=region.display_prefix,
            country_code=region.country_code,
            parent_id=region.parent_id,
            point=PointOut(lon=region.point.lon, lat=region.point.lat),
            bbox=(region.bbox.west, region.bbox.south, region.bbox.east, region.bbox.north),
            has_polygon=region.has_polygon,
            aliases=list(region.aliases),
        )


class RegionRefOut(BaseModel):
    """Referencia corta a una región (migas de pan)."""

    id: int
    level: LevelLiteral
    code: str
    name: str

    @classmethod
    def from_domain(cls, ref: RegionRef) -> "RegionRefOut":
        """Convierte una ``RegionRef`` del dominio.

        Args:
            ref: Referencia del dominio.

        Returns:
            El esquema listo para serializar.
        """
        return cls(id=ref.id, level=ref.level.value, code=ref.code, name=ref.name)


class RegionDetailOut(RegionOut):
    """Región con sus ancestros."""

    ancestors: list[RegionRefOut] = Field(description="Del más general al más cercano.")
    breadcrumb: str = Field(description='"México › Ciudad de México › Iztapalapa".')

    @classmethod
    def from_detail(cls, detail: RegionDetail) -> "RegionDetailOut":
        """Convierte un ``RegionDetail`` del dominio.

        Args:
            detail: Región con ancestros.

        Returns:
            El esquema listo para serializar.
        """
        base = RegionOut.from_domain(detail.region)
        return cls(
            **base.model_dump(),
            ancestors=[RegionRefOut.from_domain(a) for a in detail.ancestors],
            breadcrumb=detail.breadcrumb,
        )


class RegionPageOut(BaseModel):
    """Página de regiones con cursor (CLAUDE.md §6.3)."""

    items: list[RegionOut]
    next_cursor: str | None = Field(description="Pásalo como ?cursor= para la siguiente página.")

    @classmethod
    def from_page(cls, page: Page[Region]) -> "RegionPageOut":
        """Convierte una página del caso de uso.

        Args:
            page: Página de regiones.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            items=[RegionOut.from_domain(r) for r in page.items], next_cursor=page.next_cursor
        )


class RegionListOut(BaseModel):
    """Lista sin paginar (resultados de búsqueda)."""

    items: list[RegionOut]
