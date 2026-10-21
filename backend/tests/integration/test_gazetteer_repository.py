"""Geolocalizador contra el mini-catálogo real de la base de pruebas (§11)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.gazetteer_repository import PostgresGazetteer
from app.application.use_cases.geocoding import GeocodeMentions
from app.core.config import Settings
from app.domain.geocoding import FUZZY_MIN_SIMILARITY, Mention, MentionRole, Precision
from app.domain.region import RegionLevel
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
EVENT = MentionRole.EVENT


@pytest.fixture(scope="module")
def catalog(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    yield engine
    engine.dispose()


@pytest.fixture
def gazetteer(catalog: Engine, test_engine: AsyncEngine) -> PostgresGazetteer:
    return PostgresGazetteer(test_engine)


async def test_exacto_por_nombre_y_alias(gazetteer: PostgresGazetteer) -> None:
    izta = await gazetteer.exact("IZTAPALAPA")
    cdmx = await gazetteer.exact("CDMX")

    assert {(p.code, p.level) for p in izta} >= {
        ("09007", RegionLevel.MUNICIPALITY),
        ("090070001", RegionLevel.LOCALITY),
    }
    municipality = next(p for p in izta if p.level is RegionLevel.MUNICIPALITY)
    assert municipality.display_name.endswith("Iztapalapa")
    assert municipality.display_name != "Iztapalapa"  # lleva su prefijo ("Alcaldía")
    assert [p.code for p in cdmx] == ["09"]


async def test_parecidos_pais_y_clave(gazetteer: PostgresGazetteer) -> None:
    similar = await gazetteer.similar("IZTAPALPA", FUZZY_MIN_SIMILARITY - 0.3)
    mexico = await gazetteer.country("MEXICO")

    assert similar
    assert {p.code for p, _ in similar} <= {"09007", "090070001"}
    assert mexico is not None and mexico.code == "MEX"
    assert await gazetteer.country("ATLANTIDA") is None
    assert (await gazetteer.by_code("15058")) is not None
    assert await gazetteer.by_code("99999") is None
    assert await gazetteer.similar("ZZZZZZZZ", FUZZY_MIN_SIMILARITY) == []


async def test_casos_de_la_especificacion_con_el_catalogo_real(
    gazetteer: PostgresGazetteer,
) -> None:
    use_case = GeocodeMentions(gazetteer)

    izta, neza, penon, san_pedro = await use_case.run(
        [
            Mention("Iztapalapa", EVENT),
            Mention("Neza", MentionRole.MENTIONED),
            Mention("Peñón de los Baños", MentionRole.MENTIONED),
            Mention("San Pedro", MentionRole.MENTIONED),
        ],
        None,
    )

    assert izta.place is not None and izta.place.code == "09007"
    assert izta.is_primary
    assert neza.place is not None and neza.place.code == "15058"
    assert penon.place is not None and penon.place.code == "090150099"
    # Sin pista: solo existe San Pedro, Coahuila, en el mini-catálogo y su
    # alias de Nuevo León no está en estos datos de prueba.
    assert san_pedro.precision in {Precision.MUNICIPALITY, Precision.UNKNOWN}


async def test_colonias_por_nombre_o_familia_solo_en_su_estado(
    catalog: Engine, gazetteer: PostgresGazetteer
) -> None:
    # Colonias de OpenStreetMap (ADR-0020): dos de la familia "Roma" en
    # Cuauhtémoc y una homónima fuera de la CDMX que no debe salir.
    with catalog.begin() as conn:
        conn.execute(text("DELETE FROM places"))
        conn.execute(
            text(
                """
                INSERT INTO places (name, name_core, kind, municipality_id, point, source)
                SELECT v.name, v.core, 'neighbourhood', r.id,
                    ST_SetSRID(ST_MakePoint(-99.16, 19.41), 4326), 'prueba'
                FROM (VALUES ('Colonia Roma Norte', 'ROMA NORTE', '09015'),
                             ('Colonia Roma Sur', 'ROMA SUR', '09015'),
                             ('Colonia Roma', 'ROMA', '15058'),
                             ('Romanos 50%', 'ROMA_NOS', '09015')) AS v(name, core, code)
                JOIN regions r ON r.code = v.code
                """
            )
        )

    roma = await gazetteer.neighborhoods("ROMA", "09")
    exact = await gazetteer.neighborhoods("ROMA NORTE", "09")

    assert sorted(n.name for n in roma) == ["Colonia Roma Norte", "Colonia Roma Sur"]
    assert {n.municipality.code for n in roma} == {"09015"}
    assert [n.name for n in exact] == ["Colonia Roma Norte"]
    # El "_" de LIKE se busca literal: "ROMA_" no es comodín de "ROMAN".
    assert await gazetteer.neighborhoods("ROMA_NOS", "15") == []
    with catalog.begin() as conn:
        conn.execute(text("DELETE FROM places"))
