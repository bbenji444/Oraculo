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
        search_terms_csv=FIXTURES / "search_terms.csv",
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


# La fila «Mundo» que agrega la migración 0048 (ADR-0112). Al vaciar
# ``regions`` se pierde y la migración ya no vuelve a correr; en producción el
# cargador no la borra (hace upsert por clave).
WORLD_ROW = """
    INSERT INTO regions (level, code, parent_id, country_code, name, name_norm, aliases,
                         aliases_norm, display_prefix, geom, centroid, bbox, focus_bbox, source)
    VALUES ('world', 'WLD', NULL, 'WLD', 'Mundo', 'MUNDO',
            ARRAY['Todo el mundo', 'Global'], ARRAY['TODO EL MUNDO', 'GLOBAL'], '',
            ST_Multi(ST_MakeEnvelope(-180, -90, 180, 90, 4326)),
            ST_SetSRID(ST_MakePoint(0, 20), 4326),
            ARRAY[-180, -90, 180, 90]::double precision[],
            ARRAY[-180, -58, 180, 75]::double precision[], 'Monitor de Noticias (ADR-0112)')
    ON CONFLICT (code) DO NOTHING
"""


def load_fixture_catalog(engine: Engine, settings: Settings, work_dir: Path) -> LoadSummary:
    """Vacía ``regions`` en la base de pruebas y carga el mini-catálogo, con «Mundo»."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM regions"))
    summary = run_load(engine, fixture_target(settings), fixture_inputs(), work_dir)
    with engine.begin() as conn:
        conn.execute(text(WORLD_ROW))
    return summary
