"""Carga de geodatos de punta a punta sobre la base de pruebas, con el mini-catálogo."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.core.config import Settings
from app.geodata.carga import GeodataLoadError, LoadSummary, apply_aliases, run_load
from app.geodata.terminos import (
    CountryCodes,
    SearchTermsError,
    apply_country_codes,
    apply_search_terms,
    read_search_terms,
)
from tests.integration.geo_fixture import (
    FIXTURES,
    NE_SOURCE,
    fixture_inputs,
    fixture_target,
    load_fixture_catalog,
)

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
ZOCALO = (-99.1332, 19.4326)


@pytest.fixture(scope="module")
def engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    test_engine = create_engine(settings.database_url(test=True))
    yield test_engine
    test_engine.dispose()


@pytest.fixture(scope="module")
def work_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # tmp_path_factory crea la carpeta en /tmp: disco de Linux, como en producción.
    return tmp_path_factory.mktemp("geodata")


@pytest.fixture(scope="module")
def summary(engine: Engine, settings: Settings, work_dir: Path) -> LoadSummary:
    return load_fixture_catalog(engine, settings, work_dir)


def row(engine: Engine, code: str) -> dict[str, Any]:
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT r.level::text, r.name, r.name_norm, r.display_prefix, r.country_code,
                       r.aliases, r.aliases_norm, p.code AS parent_code, r.source,
                       r.geom IS NULL AS sin_poligono, r.bbox,
                       ST_IsValid(r.geom) AS valida,
                       ST_GeometryType(r.geom) AS tipo,
                       r.geom IS NULL OR ST_Intersects(r.geom, r.centroid) AS punto_dentro
                FROM regions r LEFT JOIN regions p ON p.id = r.parent_id
                WHERE r.code = :code
                """
            ),
            {"code": code},
        ).mappings()
        return dict(result.one())


def test_conteos_por_nivel(summary: LoadSummary) -> None:
    # Países: Colombia, Francia y México (este último armado con los estados).
    assert summary.counts == {"country": 3, "state": 4, "municipality": 6, "locality": 4}
    assert summary.aliases == 4


def test_mexico_es_la_union_de_los_estados_y_no_natural_earth(engine: Engine) -> None:
    mexico = row(engine, "MEX")

    assert mexico["name"] == "México"
    assert mexico["source"] != NE_SOURCE
    # El contorno de Natural Earth del fixture llega a -118; los estados no.
    assert mexico["bbox"][0] == pytest.approx(-103.97)


def test_pais_con_iso_menos_99_usa_adm0(engine: Engine) -> None:
    francia = row(engine, "FRA")

    assert (francia["name"], francia["display_prefix"], francia["level"]) == (
        "Francia",
        "País",
        "country",
    )


def test_jerarquia_y_prefijos(engine: Engine) -> None:
    iztapalapa = row(engine, "09007")
    cdmx = row(engine, "09")
    neza = row(engine, "15058")

    assert (iztapalapa["parent_code"], iztapalapa["display_prefix"]) == ("09", "Alcaldía")
    assert (cdmx["parent_code"], cdmx["display_prefix"]) == ("MEX", "Entidad federativa")
    assert (neza["parent_code"], neza["display_prefix"]) == ("15", "Municipio")
    assert row(engine, "15")["display_prefix"] == "Estado"


def test_nombres_originales_y_normalizados_con_enie(engine: Engine) -> None:
    penon = row(engine, "090150099")

    assert penon["name"] == "Peñón de los Baños"
    assert penon["name_norm"] == "PEÑON DE LOS BAÑOS"
    assert penon["parent_code"] == "09015"


def test_alias_aplicados_y_normalizados(engine: Engine) -> None:
    cdmx = row(engine, "09")

    assert cdmx["aliases"] == ["CDMX", "la capital del país"]
    assert cdmx["aliases_norm"] == ["CDMX", "LA CAPITAL DEL PAIS"]


def test_poligono_invalido_se_repara(summary: LoadSummary, engine: Engine) -> None:
    acuna = row(engine, "05002")

    assert summary.repaired["inegi_mun"] == 1
    assert acuna["valida"] is True
    assert acuna["tipo"] == "ST_MultiPolygon"


def test_punto_representativo_siempre_dentro(engine: Engine) -> None:
    for code in ("MEX", "09", "15", "09007", "05002", "090070001"):
        assert row(engine, code)["punto_dentro"], code


def test_localidad_puntual_sin_poligono_y_bbox_de_un_punto(engine: Engine) -> None:
    canada = row(engine, "050020050")

    assert canada["sin_poligono"] is True
    assert canada["bbox"] == [-101.2, 29.1, -101.2, 29.1]


def test_si_una_clave_esta_en_ambas_capas_gana_el_poligono(engine: Engine) -> None:
    localidad = row(engine, "090070001")

    assert localidad["name"] == "Iztapalapa"
    assert localidad["sin_poligono"] is False


def test_zocalo_cae_en_cuauhtemoc_cdmx_y_mexico(engine: Engine) -> None:
    with engine.connect() as conn:
        codes = conn.execute(
            text(
                "SELECT code FROM regions "
                "WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) "
                "ORDER BY code"
            ),
            {"lon": ZOCALO[0], "lat": ZOCALO[1]},
        ).scalars()
        assert list(codes) == ["09", "09015", "MEX"]


def test_el_estado_de_mexico_no_cubre_a_la_cdmx(engine: Engine) -> None:
    with engine.connect() as conn:
        contains = conn.execute(
            text(
                "SELECT ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) "
                "FROM regions WHERE code = '15'"
            ),
            {"lon": ZOCALO[0], "lat": ZOCALO[1]},
        ).scalar_one()
    assert contains is False


def test_volver_a_cargar_no_duplica_ni_cambia_ids(
    engine: Engine, settings: Settings, work_dir: Path
) -> None:
    def ids() -> dict[str, int]:
        with engine.connect() as conn:
            return dict(conn.execute(text("SELECT code, id FROM regions")).all())

    before = ids()

    # Sin borrar nada: la segunda carga debe actualizar en su lugar (upsert).
    again = run_load(engine, fixture_target(settings), fixture_inputs(), work_dir)

    with engine.connect() as conn:
        staging = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'staging_geo'"
            )
        ).scalar_one()
    assert again.counts == {"country": 3, "state": 4, "municipality": 6, "locality": 4}
    assert ids() == before
    assert staging == 0


def test_alias_con_clave_inexistente_es_error(engine: Engine) -> None:
    with pytest.raises(GeodataLoadError, match="99999"):
        apply_aliases(engine, {"99999": ["Inventado"]})


def search_terms_and_codes(engine: Engine, code: str) -> tuple[Any, ...]:
    with engine.connect() as conn:
        return tuple(
            conn.execute(
                text(
                    "SELECT search_terms, iso_a2, fips_code, name_en FROM regions WHERE code = :c"
                ),
                {"c": code},
            ).one()
        )


def test_terminos_de_busqueda_aplicados(summary: LoadSummary, engine: Engine) -> None:
    assert summary.search_terms == 2
    assert search_terms_and_codes(engine, "09")[0] == ["Ciudad de México", "CDMX"]
    assert search_terms_and_codes(engine, "15")[0] == ["Estado de México", "Edomex"]
    # Sin entrada en la lista: vacío, y la consulta usará su nombre.
    assert search_terms_and_codes(engine, "09007")[0] == []


def test_codigos_de_pais_aplicados_con_la_misma_clave_del_cargador(
    summary: LoadSummary, engine: Engine
) -> None:
    assert summary.country_codes == 3
    assert search_terms_and_codes(engine, "MEX")[1:] == ("MX", "MX", "Mexico")
    assert search_terms_and_codes(engine, "COL")[1:] == ("CO", "CO", "Colombia")
    # Francia entra con clave ADM0 (ISO_A3 = -99); su FIPS -99 del fixture queda vacío.
    assert search_terms_and_codes(engine, "FRA")[1:] == ("FR", None, "France")


def test_quitar_un_termino_del_csv_lo_quita_de_la_base(engine: Engine) -> None:
    try:
        apply_search_terms(engine, {"09": ["CDMX"]})

        assert search_terms_and_codes(engine, "09")[0] == ["CDMX"]
        assert search_terms_and_codes(engine, "15")[0] == []
    finally:
        apply_search_terms(engine, read_search_terms(FIXTURES / "search_terms.csv"))


def test_termino_con_clave_inexistente_es_error(engine: Engine) -> None:
    with pytest.raises(SearchTermsError, match="99999"):
        apply_search_terms(engine, {"99999": ["Inventado"]})


def test_pais_de_natural_earth_sin_region_es_error(engine: Engine) -> None:
    with pytest.raises(SearchTermsError, match="ZZZ"):
        apply_country_codes(engine, [CountryCodes("ZZZ", "ZZ", None, "Nowhere")])
