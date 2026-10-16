"""Mini-catálogo geográfico de prueba, cargado con el mismo cargador real.

Lo usan las pruebas del cargador y, después, las de los endpoints de
regiones. Los datos están en ``tests/fixtures/geo/``: coordenadas
aproximadas a las reales, con casos difíciles a propósito (dos "San Pedro",
un polígono inválido, una clave repetida entre capas, Ñ y acentos).
"""

from pathlib import Path

from sqlalchemy import Engine, text

from app.core.config import Settings
from app.geodata.carga import LayerInput, LoadInputs, LoadSummary, PostgresTarget, run_load

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "geo"
INEGI_FIELDS = ("CVEGEO", "NOMGEO")
INEGI_SOURCE = "INEGI prueba"
NE_SOURCE = "Natural Earth prueba"


def fixture_inputs() -> LoadInputs:
    def layer(table: str, filename: str, *, is_point: bool = False) -> LayerInput:
        return LayerInput(table, FIXTURES / filename, "utf-8", is_point, INEGI_FIELDS)

    return LoadInputs(
        countries=LayerInput(
            "ne_countries",
            FIXTURES / "paises.geojson",
            "utf-8",
            False,
            ("ADM0_A3", "ISO_A3", "NAME_ES", "NAME"),
        ),
        states=layer("inegi_ent", "00ent.geojson"),
        municipalities=layer("inegi_mun", "00mun.geojson"),
        locality_points=layer("inegi_lpr", "00lpr.geojson", is_point=True),
        locality_polygons=layer("inegi_l", "00l.geojson"),
        aliases_csv=FIXTURES / "aliases.csv",
        inegi_source=INEGI_SOURCE,
        natural_earth_source=NE_SOURCE,
    )


def fixture_target(settings: Settings) -> PostgresTarget:
    return PostgresTarget(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_test_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )


def load_fixture_catalog(engine: Engine, settings: Settings, work_dir: Path) -> LoadSummary:
    """Vacía ``regions`` en la base de pruebas y carga el mini-catálogo."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM regions"))
    return run_load(engine, fixture_target(settings), fixture_inputs(), work_dir)
