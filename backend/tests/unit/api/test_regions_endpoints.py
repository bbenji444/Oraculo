"""Endpoints /api/v1/regions con el repositorio reemplazado por uno en memoria."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.regions import get_region_repository
from app.main import create_app
from tests.unit.fake_regions import CUAUHTEMOC, FakeRegionRepository


@pytest.fixture
def repository() -> FakeRegionRepository:
    return FakeRegionRepository()


@pytest.fixture
def client(repository: FakeRegionRepository) -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_region_repository] = lambda: repository
    # Sin `with`: no corre el lifespan, así que no se conecta a la base.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_lista_por_nivel_con_cursor(client: TestClient) -> None:
    first = client.get("/api/v1/regions", params={"level": "municipality", "limit": 2}).json()
    second = client.get(
        "/api/v1/regions",
        params={"level": "municipality", "limit": 2, "cursor": first["next_cursor"]},
    ).json()

    assert [r["name"] for r in first["items"]] == ["Cuauhtémoc", "Iztacalco"]
    assert [r["name"] for r in second["items"]] == ["Iztapalapa"]
    assert second["next_cursor"] is None


def test_forma_de_una_region(client: TestClient) -> None:
    body = client.get("/api/v1/regions/3").json()

    assert body["display_name"] == "Alcaldía Iztapalapa"
    assert body["bbox"] == [-99.1, 18.9, -98.9, 19.1]
    # Región de una sola parte: el encuadre es el mismo bbox.
    assert body["focus_bbox"] == body["bbox"]
    assert body["point"] == {"lon": -99.0, "lat": 19.0}
    assert body["breadcrumb"] == "México › Ciudad de México › Iztapalapa"
    assert [a["code"] for a in body["ancestors"]] == ["MEX", "09"]
    assert "geom" not in body


def test_hijas(client: TestClient) -> None:
    body = client.get("/api/v1/regions/2/children").json()

    assert [r["code"] for r in body["items"]] == ["09015", "09006", "09007"]


def test_busqueda(client: TestClient) -> None:
    body = client.get("/api/v1/regions/search", params={"q": "izta"}).json()

    assert {r["name"] for r in body["items"]} == {"Iztapalapa", "Iztacalco"}


def test_region_en_un_punto(client: TestClient, repository: FakeRegionRepository) -> None:
    repository.point_result = CUAUHTEMOC

    response = client.get(
        "/api/v1/regions/at", params={"lon": -99.1332, "lat": 19.4326, "level": "municipality"}
    )

    assert response.status_code == 200
    assert response.json()["code"] == "09015"


# --- Formato uniforme de errores (§13) -------------------------------------------


def test_region_inexistente_responde_404_uniforme(client: TestClient) -> None:
    response = client.get("/api/v1/regions/999")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "region_not_found",
            "message": "No existe esa región.",
            "details": {"id": 999},
        }
    }


def test_busqueda_muy_corta_responde_422_en_espanol(client: TestClient) -> None:
    response = client.get("/api/v1/regions/search", params={"q": "a"})

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Escribe al menos 2 letras para buscar."


def test_parametro_faltante_responde_422_uniforme(client: TestClient) -> None:
    response = client.get("/api/v1/regions")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["message"] == "Parámetros inválidos o faltantes: level."
    assert error["details"]["problemas"][0]["parametro"] == "level"


def test_nivel_invalido_responde_422(client: TestClient) -> None:
    response = client.get("/api/v1/regions", params={"level": "colonia"})

    assert response.status_code == 422


def test_ruta_inexistente_responde_404_uniforme(client: TestClient) -> None:
    response = client.get("/api/v1/no-existe")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_metodo_no_permitido_responde_405_uniforme(client: TestClient) -> None:
    response = client.post("/api/v1/regions/3")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_endpoints_documentados_en_openapi(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]

    assert {
        "/api/v1/regions",
        "/api/v1/regions/search",
        "/api/v1/regions/at",
        "/api/v1/regions/{region_id}",
        "/api/v1/regions/{region_id}/children",
    } <= set(paths)
