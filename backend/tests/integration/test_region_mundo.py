"""Región «Mundo» con el mini-catálogo real de PostGIS (ADR-0112).

Se prueba el SQL que la trata distinto de un país: los datos para armar la
consulta (sin país), el «¿qué hay en este punto?» (nunca «Mundo») y el mapa
del reporte (los países).
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.reports.static_map import PostgisStaticMap
from app.application.ports.reports import SubregionCount
from app.core.config import Settings
from app.domain.aggregates import AggregateLevel
from app.domain.region import WORLD_CODE, GeoPoint, RegionLevel
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
# Un punto en medio del Atlántico: ningún país lo contiene.
ATLANTIC = GeoPoint(-40.0, 30.0)


@pytest.fixture(scope="module")
def catalog(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    yield engine
    engine.dispose()


async def test_mundo_no_filtra_por_pais(catalog: Engine, test_engine: AsyncEngine) -> None:
    regions = PostgresRegionRepository(test_engine)
    world = await regions.get_by_code(WORLD_CODE)
    assert world is not None
    assert world.level is RegionLevel.WORLD
    assert world.parent_id is None

    facts = await regions.place_facts(world.id)

    assert facts is not None
    assert facts.level is RegionLevel.WORLD
    assert facts.country.worldwide
    assert facts.country.iso_a2 is None
    assert facts.country.fips_code is None


async def test_un_pais_sigue_con_su_codigo(catalog: Engine, test_engine: AsyncEngine) -> None:
    # El LEFT JOIN de «Mundo» no cambia a los países.
    regions = PostgresRegionRepository(test_engine)
    mexico = await regions.get_by_code("MEX")
    assert mexico is not None

    facts = await regions.place_facts(mexico.id)

    assert facts is not None
    assert not facts.country.worldwide
    assert facts.country.iso_a2 == "MX"


async def test_un_punto_nunca_es_mundo(catalog: Engine, test_engine: AsyncEngine) -> None:
    regions = PostgresRegionRepository(test_engine)

    assert await regions.find_at_point(ATLANTIC, None) is None
    assert await regions.find_at_point(ATLANTIC, RegionLevel.WORLD) is None


async def test_se_encuentra_por_su_nombre_y_alias(
    catalog: Engine, test_engine: AsyncEngine
) -> None:
    regions = PostgresRegionRepository(test_engine)

    assert WORLD_CODE in [r.code for r in await regions.search("MUNDO", 10)]
    assert WORLD_CODE in [r.code for r in await regions.search("TODO EL MUNDO", 10)]


async def test_el_mapa_del_mundo_pinta_los_paises(
    catalog: Engine, test_engine: AsyncEngine
) -> None:
    world = await PostgresRegionRepository(test_engine).get_by_code(WORLD_CODE)
    assert world is not None

    svg = await PostgisStaticMap(test_engine).render(
        world,
        AggregateLevel.COUNTRY,
        [SubregionCount("MEX", "México", 3), SubregionCount("FRA", "Francia", 1)],
        [],
    )

    assert "<title>México: 3</title>" in svg
    assert "<title>Francia: 1</title>" in svg
    # Sin contorno: el del mundo sería un rectángulo alrededor de todo.
    assert not re.search(r'fill="none" stroke="[^"]+" stroke-width', svg)
