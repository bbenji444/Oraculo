"""Endpoints /api/v1/categories con un catálogo en memoria (editor de subdivisiones)."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.categories import get_category_store
from app.api.v1.concepts import get_actor
from app.application.audit import Actor
from app.domain.categories import Category
from app.main import create_app
from tests.unit.application.test_catalog import FakeCatalog

URL = "/api/v1/categories"
HOMICIDIO = Category(5, "Homicidio", "Asesinatos", color="#FF4D6D", topic_concept_id=21)
APAGADA = Category(13, "Delitos electorales", "Compra de votos", is_active=False)
OTROS = Category(14, "Otros", "Lo demás", is_other=True)


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog(HOMICIDIO, APAGADA, OTROS)


@pytest.fixture
def client(catalog: FakeCatalog) -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_category_store] = lambda: catalog
    app.dependency_overrides[get_actor] = lambda: Actor("prueba", "127.0.0.1")
    # Sin `with`: no corre el lifespan, así que no se conecta a la base.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_por_omision_solo_las_activas_con_su_tema(client: TestClient) -> None:
    items = client.get(URL).json()["items"]

    assert [i["id"] for i in items] == [5, 14]
    assert items[0]["topic_concept_id"] == 21
    assert items[0]["is_active"] is True


def test_el_editor_tambien_ve_las_apagadas(client: TestClient) -> None:
    items = client.get(URL, params={"include_inactive": "true"}).json()["items"]

    assert [(i["id"], i["is_active"]) for i in items] == [(5, True), (13, False), (14, True)]


def test_editar_devuelve_la_subdivision_como_quedo(
    client: TestClient, catalog: FakeCatalog
) -> None:
    response = client.patch(f"{URL}/5", json={"color": "#ff0000", "name": "Homicidio doloso"})

    assert response.status_code == 200
    assert response.json()["name"] == "Homicidio doloso"
    assert response.json()["color"] == "#FF0000"
    assert catalog.audit[0].actor.user_id == "prueba"


def test_errores_del_editor(client: TestClient) -> None:
    missing = client.patch(f"{URL}/99", json={"name": "X"})
    invalid = client.patch(f"{URL}/14", json={"is_active": False})

    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "category_not_found")
    assert (invalid.status_code, invalid.json()["error"]["code"]) == (422, "invalid_category")
    assert invalid.json()["error"]["details"]["problemas"][0]["campo"] == "is_active"
