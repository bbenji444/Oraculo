"""Endpoints /regions de punta a punta contra PostGIS con el mini-catálogo.

Arranca la aplicación real (con su lifespan) apuntando a la base de
pruebas, carga el mini-catálogo con el cargador real y hace peticiones HTTP.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import Settings
from app.main import create_app
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
ZOCALO = {"lon": -99.1332, "lat": 19.4326}


@pytest.fixture(scope="module")
def client(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    engine.dispose()
    test_settings = settings.model_copy(update={"postgres_db": settings.postgres_test_db})
    with TestClient(create_app(test_settings)) as test_client:
        yield test_client


def get(client: TestClient, path: str, **params: Any) -> Any:
    response = client.get(f"/api/v1/regions{path}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_busqueda_izta_devuelve_iztapalapa_primero(client: TestClient) -> None:
    items = get(client, "/search", q="izta")["items"]

    # El municipio va antes que la localidad del mismo nombre.
    assert [(r["code"], r["level"]) for r in items][:2] == [
        ("09007", "municipality"),
        ("090070001", "locality"),
    ]
    assert items[0]["display_name"] == "Alcaldía Iztapalapa"


@pytest.mark.parametrize(
    ("query", "expected_code"),
    [("cdmx", "09"), ("la capital del pais", "09"), ("neza", "15058"), ("EDOMEX", "15")],
)
def test_busqueda_por_alias(client: TestClient, query: str, expected_code: str) -> None:
    assert get(client, "/search", q=query)["items"][0]["code"] == expected_code


def test_busqueda_sin_acentos_y_con_enie(client: TestClient) -> None:
    assert get(client, "/search", q="cuauhtemoc")["items"][0]["code"] == "09015"
    assert get(client, "/search", q="peñon")["items"][0]["name"] == "Peñón de los Baños"


def test_busqueda_con_error_de_escritura_por_trigramas(client: TestClient) -> None:
    codes = [r["code"] for r in get(client, "/search", q="iztapalpa")["items"]]

    assert "09007" in codes


def test_busqueda_san_pedro_devuelve_ambos(client: TestClient) -> None:
    codes = {r["code"] for r in get(client, "/search", q="san pedro")["items"]}

    assert {"05033", "19019"} <= codes


def test_busqueda_con_comodines_se_toma_literal(client: TestClient) -> None:
    assert get(client, "/search", q="%%")["items"] == []


def test_zocalo_en_municipio_es_cuauhtemoc(client: TestClient) -> None:
    body = get(client, "/at", level="municipality", **ZOCALO)

    assert (body["code"], body["display_name"]) == ("09015", "Alcaldía Cuauhtémoc")


def test_zocalo_sin_nivel_devuelve_la_region_mas_especifica(client: TestClient) -> None:
    assert get(client, "/at", **ZOCALO)["code"] == "09015"


@pytest.mark.parametrize(("level", "code"), [("state", "09"), ("country", "MEX")])
def test_zocalo_en_estado_y_pais(client: TestClient, level: str, code: str) -> None:
    assert get(client, "/at", level=level, **ZOCALO)["code"] == code


def test_punto_en_colombia(client: TestClient) -> None:
    assert get(client, "/at", lon=-74.08, lat=4.6)["code"] == "COL"


def test_punto_en_el_mar_responde_404_uniforme(client: TestClient) -> None:
    response = client.get("/api/v1/regions/at", params={"lon": -130.0, "lat": 10.0})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "region_not_found"


def test_estados_paginados_en_orden_alfabetico_sin_repetir(client: TestClient) -> None:
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"level": "state", "limit": 1}
        if cursor:
            params["cursor"] = cursor
        page = get(client, "", **params)
        seen += [r["name"] for r in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == ["Ciudad de México", "Coahuila de Zaragoza", "México", "Nuevo León"]


def test_detalle_con_migas_de_pan(client: TestClient) -> None:
    iztapalapa_id = get(client, "/search", q="iztapalapa")["items"][0]["id"]

    body = get(client, f"/{iztapalapa_id}")

    assert body["breadcrumb"] == "México › Ciudad de México › Iztapalapa"
    assert [a["level"] for a in body["ancestors"]] == ["country", "state"]


def test_hijas_de_la_cdmx(client: TestClient) -> None:
    cdmx_id = get(client, "/search", q="cdmx")["items"][0]["id"]

    names = [r["name"] for r in get(client, f"/{cdmx_id}/children")["items"]]

    assert names == ["Cuauhtémoc", "Iztapalapa"]


def test_pais_con_territorios_lejanos_encuadra_su_parte_principal(client: TestClient) -> None:
    francia = get(client, "/search", q="francia")["items"][0]

    assert francia["bbox"][0] == pytest.approx(-54.5)
    assert francia["focus_bbox"] == pytest.approx([-5, 41.4, 9.5, 51])


def test_localidad_puntual_sin_poligono(client: TestClient) -> None:
    body = get(client, "/search", q="la canada")["items"][0]

    assert body["has_polygon"] is False
    assert body["bbox"] == [-101.2, 29.1, -101.2, 29.1]
