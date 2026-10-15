"""Criterios de aceptación de §12 sobre el mini-catálogo de pruebas."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine

from app.core.config import Settings
from app.geodata.validacion import Expectations, run_checks
from app.geodata.validar import build_expectations
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]

FIXTURE_CATALOG = {
    "09015": "Cuauhtémoc",
    "09007": "Iztapalapa",
    "15058": "Nezahualcóyotl",
    "05033": "San Pedro",
    "19019": "San Pedro Garza García",
    "05002": "Acuña",
}
FIXTURE_EXPECTATIONS = Expectations(
    state_count=4,
    cdmx_municipality_count=2,
    catalog_municipalities=FIXTURE_CATALOG,
    locality_count=4,
    locality_polygon_count=2,
    min_enie_names=1,
)


@pytest.fixture(scope="module")
def conn(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Connection]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def test_todas_las_revisiones_pasan_con_el_mini_catalogo(conn: Connection) -> None:
    results = run_checks(conn, FIXTURE_EXPECTATIONS)

    assert [r.name for r in results if not r.passed] == []
    assert len(results) == 11


def test_detecta_conteo_de_entidades_incorrecto(conn: Connection) -> None:
    results = {r.name: r for r in run_checks(conn, replace(FIXTURE_EXPECTATIONS, state_count=32))}

    assert results["Entidades federativas"].passed is False
    assert results["Entidades federativas"].actual == "4"


def test_detecta_nombre_con_enie_mal_leido(conn: Connection) -> None:
    # Así se vería "Acuña" si se hubiera leído UTF-8 como latin1.
    broken = {**FIXTURE_CATALOG, "05002": "AcuÃ±a"}

    results = {
        r.name: r
        for r in run_checks(conn, replace(FIXTURE_EXPECTATIONS, catalog_municipalities=broken))
    }

    check = results["Nombres con Ñ idénticos al catálogo"]
    assert check.passed is False


def test_detecta_municipio_faltante(conn: Connection) -> None:
    catalog = {**FIXTURE_CATALOG, "09999": "Fantasma"}

    results = {
        r.name: r
        for r in run_checks(conn, replace(FIXTURE_EXPECTATIONS, catalog_municipalities=catalog))
    }

    check = results["Municipios = catálogo oficial (claves)"]
    assert check.passed is False
    assert "09999" in check.actual


def test_expectativas_reales_desde_la_inspeccion() -> None:
    inspection = {"localities": {"distinct": 296_850, "polygons": 51_798}}

    expectations = build_expectations(inspection, {"09007": "Iztapalapa"})

    assert expectations.state_count == 32
    assert expectations.cdmx_municipality_count == 16
    assert expectations.locality_count == 296_850
    assert expectations.locality_polygon_count == 51_798
    assert expectations.min_enie_names == 5
