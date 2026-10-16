"""Repositorio de regiones en memoria para pruebas unitarias (sin base de datos)."""

from app.application.pagination import NameCursor
from app.domain.names import normalize_name
from app.domain.queries import CountryFilter, PlaceFacts
from app.domain.region import BoundingBox, GeoPoint, Region, RegionLevel, RegionRef

MEXICO_FILTER = CountryFilter("México", "MX", "MX", "Mexico")


def make_region(
    region_id: int,
    name: str,
    level: RegionLevel = RegionLevel.MUNICIPALITY,
    *,
    parent_id: int | None = None,
    code: str | None = None,
    prefix: str = "Municipio",
    aliases: tuple[str, ...] = (),
) -> Region:
    return Region(
        id=region_id,
        level=level,
        code=code or str(region_id),
        name=name,
        name_norm=normalize_name(name),
        display_prefix=prefix,
        country_code="MEX",
        parent_id=parent_id,
        point=GeoPoint(-99.0, 19.0),
        bbox=BoundingBox(-99.1, 18.9, -98.9, 19.1),
        has_polygon=True,
        aliases=aliases,
        population=None,
    )


MEXICO = make_region(1, "México", RegionLevel.COUNTRY, code="MEX", prefix="País")
CDMX = make_region(
    2,
    "Ciudad de México",
    RegionLevel.STATE,
    parent_id=1,
    code="09",
    prefix="Entidad federativa",
    aliases=("CDMX",),
)
IZTAPALAPA = make_region(3, "Iztapalapa", parent_id=2, code="09007", prefix="Alcaldía")
CUAUHTEMOC = make_region(4, "Cuauhtémoc", parent_id=2, code="09015", prefix="Alcaldía")
IZTACALCO = make_region(5, "Iztacalco", parent_id=2, code="09006", prefix="Alcaldía")
ALL = (MEXICO, CDMX, IZTAPALAPA, CUAUHTEMOC, IZTACALCO)


class FakeRegionRepository:
    """Implementa ``RegionRepositoryPort`` con una lista en memoria."""

    def __init__(self, regions: tuple[Region, ...] = ALL) -> None:
        self.regions = {r.id: r for r in regions}
        self.last_search: tuple[str, int] | None = None
        self.last_point: tuple[GeoPoint, RegionLevel | None] | None = None
        self.point_result: Region | None = None
        # Términos curados por clave, como geodata/search_terms.csv.
        self.search_terms: dict[str, tuple[str, ...]] = {"09": ("Ciudad de México", "CDMX")}

    def _page(self, items: list[Region], after: NameCursor | None, limit: int) -> list[Region]:
        ordered = sorted(items, key=lambda r: (r.name_norm, r.id))
        if after:
            ordered = [r for r in ordered if (r.name_norm, r.id) > (after.name_norm, after.id)]
        return ordered[:limit]

    async def list_by_level(
        self, level: RegionLevel, after: NameCursor | None, limit: int
    ) -> list[Region]:
        return self._page([r for r in self.regions.values() if r.level is level], after, limit)

    async def list_children(
        self, parent_id: int, after: NameCursor | None, limit: int
    ) -> list[Region]:
        children = [r for r in self.regions.values() if r.parent_id == parent_id]
        return self._page(children, after, limit)

    async def get(self, region_id: int) -> Region | None:
        return self.regions.get(region_id)

    async def get_by_code(self, code: str) -> Region | None:
        return next((r for r in self.regions.values() if r.code == code), None)

    async def ancestors(self, region_id: int) -> list[RegionRef]:
        chain: list[RegionRef] = []
        current = self.regions[region_id].parent_id
        while current is not None:
            parent = self.regions[current]
            chain.insert(0, parent.ref())
            current = parent.parent_id
        return chain

    async def search(self, query_norm: str, limit: int) -> list[Region]:
        self.last_search = (query_norm, limit)
        return [r for r in self.regions.values() if query_norm in r.name_norm][:limit]

    async def place_facts(self, region_id: int) -> PlaceFacts | None:
        region = self.regions.get(region_id)
        if region is None:
            return None
        state = next(
            (
                self.regions[ref.id]
                for ref in await self.ancestors(region_id)
                if ref.level is RegionLevel.STATE
            ),
            None,
        )
        repeated = any(
            r.id != region.id and r.level is region.level and r.name_norm == region.name_norm
            for r in self.regions.values()
        )
        return PlaceFacts(
            level=region.level,
            name=region.name,
            search_terms=self.search_terms.get(region.code, ()),
            name_is_repeated=repeated,
            state_name=state.name if state else None,
            state_search_terms=self.search_terms.get(state.code, ()) if state else (),
            country=MEXICO_FILTER,
        )

    async def find_at_point(self, point: GeoPoint, level: RegionLevel | None) -> Region | None:
        self.last_point = (point, level)
        return self.point_result
