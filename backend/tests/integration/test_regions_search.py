"""Orden del buscador de regiones con el mini-catálogo real de PostGIS (§14.2).

Lo que se prueba es el SQL de ``PostgresRegionRepository.search``: qué región
sale primero cuando la persona escribe con un error de dedo.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.core.config import Settings
from app.domain.names import normalize_name
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Dos regiones que el mini-catálogo no trae: un país lejano y un municipio
# cuyo nombre se parece mucho más a lo que se escribe.
_EXTRA = """
    INSERT INTO regions (level, code, parent_id, country_code, name, name_norm,
                         display_prefix, geom, centroid, bbox, source)
    VALUES (:level, :code, :parent_id, :country_code, :name, :name_norm, :prefix,
            ST_Multi(ST_MakeEnvelope(:west, :south, :east, :north, 4326)),
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
            ARRAY[:west, :south, :east, :north], 'prueba')
"""


@pytest.fixture(scope="module")
def catalog(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    with engine.begin() as conn:
        nuevo_leon = conn.execute(text("SELECT id FROM regions WHERE code = '19'")).scalar_one()
        for row in (
            {
                "level": "country",
                "code": "MNE",
                "parent_id": None,
                "country_code": "MNE",
                "name": "Montenegro",
                "name_norm": normalize_name("Montenegro"),
                "prefix": "País",
                "lon": 19.3,
                "lat": 42.7,
                "west": 18.4,
                "south": 41.8,
                "east": 20.4,
                "north": 43.6,
            },
            {
                "level": "municipality",
                "code": "19039",
                "parent_id": nuevo_leon,
                "country_code": "MEX",
                "name": "Monterrey",
                "name_norm": normalize_name("Monterrey"),
                "prefix": "Municipio",
                "lon": -100.3,
                "lat": 25.7,
                "west": -100.4,
                "south": 25.6,
                "east": -100.2,
                "north": 25.8,
            },
        ):
            conn.execute(text(_EXTRA), row)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM regions WHERE code IN ('MNE', '19039')"))
    engine.dispose()


async def test_con_error_de_dedo_gana_lo_mas_parecido_y_no_el_nivel(
    catalog: Engine, test_engine: AsyncEngine
) -> None:
    # Prueba operativa del 20/10/2026: "monterey" ponía primero Montenegro (un
    # país, parecido 0.4) y después el municipio Monterrey (parecido 0.6).
    found = await PostgresRegionRepository(test_engine).search(normalize_name("monterey"), 10)

    assert [r.name for r in found[:2]] == ["Monterrey", "Montenegro"]


async def test_lo_exacto_y_lo_que_empieza_igual_sigue_primero_por_nivel(
    catalog: Engine, test_engine: AsyncEngine
) -> None:
    # Sin errores de dedo el orden no cambia: el estado antes que sus municipios.
    found = await PostgresRegionRepository(test_engine).search(normalize_name("nuevo"), 10)

    assert found[0].name == "Nuevo León"
    # "San Pedro" exacto gana a "San Pedro Garza García", que solo empieza igual.
    exact = await PostgresRegionRepository(test_engine).search(normalize_name("san pedro"), 10)
    assert [r.name for r in exact[:2]] == ["San Pedro", "San Pedro Garza García"]
