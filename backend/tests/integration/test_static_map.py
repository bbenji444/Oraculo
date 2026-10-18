"""Mapa estático en SVG con el mini-catálogo real de PostGIS (§15, ADR-0018)."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.reports.static_map import CONTEXT_FILL, PostgisStaticMap, fill_for
from app.application.ports.reports import MapPoint, SubregionCount
from app.core.config import Settings
from app.domain.aggregates import AggregateLevel
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def catalog(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    yield engine
    engine.dispose()


async def test_la_cdmx_con_sus_alcaldias_vecinos_y_puntos(
    catalog: Engine, test_engine: AsyncEngine
) -> None:
    cdmx = await PostgresRegionRepository(test_engine).get_by_code("09")
    assert cdmx is not None
    counts = [SubregionCount("09007", "Iztapalapa", 3), SubregionCount("09015", "Cuauhtémoc", 1)]
    points = [MapPoint(-99.05, 19.35, coarse=False), MapPoint(-99.13, 19.43, coarse=True)]

    svg = await PostgisStaticMap(test_engine).render(
        cdmx, AggregateLevel.MUNICIPALITY, counts, points
    )

    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert svg.endswith("</svg>")
    # Las dos alcaldías con su color: Iztapalapa (3) en la clase más alta (3 clases).
    assert "<title>Iztapalapa: 3</title>" in svg
    assert "<title>Cuauhtémoc: 1</title>" in svg
    assert f'fill="{fill_for(3, 3)}"><title>Iztapalapa' in svg
    # El Estado de México de fondo, el contorno y los nombres.
    assert f'<g fill="{CONTEXT_FILL}"' in svg
    assert svg.count("<path") >= 4
    assert ">Iztapalapa</text>" in svg
    # Un punto lleno y un anillo punteado (solo estado).
    assert len(re.findall(r"<circle", svg)) == 2
    assert "stroke-dasharray" in svg
    # Coordenadas acotadas: el SVG de una entidad pequeña pesa poco.
    assert len(svg) < 50_000


async def test_otro_pais_se_dibuja_a_si_mismo(catalog: Engine, test_engine: AsyncEngine) -> None:
    francia = await PostgresRegionRepository(test_engine).get_by_code("FRA")
    assert francia is not None

    svg = await PostgisStaticMap(test_engine).render(
        francia, AggregateLevel.COUNTRY, [SubregionCount("FRA", "Francia", 2)], []
    )

    assert "<title>Francia: 2</title>" in svg
