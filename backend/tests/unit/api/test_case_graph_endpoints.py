"""Endpoints del muro de un caso y de «Mis casos» con repositorios en memoria (Fase 9.6)."""

from collections.abc import Iterator
from dataclasses import replace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.case_graph import get_case_graph_repository, get_case_max_visible_nodes
from app.api.v1.cases import get_case_repository
from app.api.v1.concepts import get_actor
from app.api.v1.entities import get_entity_repository
from app.api.v1.relationships import get_relationship_repository
from app.application.audit import Actor
from app.application.ports.case_graph import CaseOnMap
from app.domain.investigation import LegalStatus, ReviewStatus
from app.main import create_app
from tests.unit.application.test_case_graph_use_cases import MIGUEL_HIDALGO, FakePoints, note
from tests.unit.application.test_entities_use_cases import person
from tests.unit.fake_cases import FakeCaseRepository
from tests.unit.fake_entities import FakeEntityRepository
from tests.unit.fake_relationships import FakeRelationshipRepository, suggested


class World:
    """Repositorios y quién pide."""

    def __init__(self) -> None:
        self.cases = FakeCaseRepository()
        self.entities = FakeEntityRepository()
        self.relationships = FakeRelationshipRepository()
        self.points = FakePoints(notes=(note(10), note(11)))
        self.actor = Actor("benji", "127.0.0.1")


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_case_repository] = lambda: world.cases
    app.dependency_overrides[get_entity_repository] = lambda: world.entities
    app.dependency_overrides[get_relationship_repository] = lambda: world.relationships
    app.dependency_overrides[get_case_graph_repository] = lambda: world.points
    app.dependency_overrides[get_case_max_visible_nodes] = lambda: 150
    app.dependency_overrides[get_actor] = lambda: world.actor
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_el_muro_trae_nodos_con_posicion_y_arcos(client: TestClient, world: World) -> None:
    case_id = UUID(client.post("/api/v1/cases", json={"name": "Caso Polanco"}).json()["id"])
    for entity_id in (1, 2):
        world.entities.add_entity(
            case_id,
            replace(
                person(entity_id),
                review_status=ReviewStatus.CONFIRMED,
                legal_status=LegalStatus.VICTIM,
            ),
        )
    world.relationships.views[case_id] = [suggested(1, 2)]

    body = client.get(f"/api/v1/cases/{case_id}/graph").json()

    assert body["name"] == "Caso Polanco"
    assert [n["legal_status_label"] for n in body["nodes"]] == ["víctima", "víctima"]
    assert all(isinstance(n["lon"], float) for n in body["nodes"])
    assert body["edges"][0]["type_label"] == "aparecen juntas"
    assert body["note_links"] == [{"first": 10, "second": 11, "shared": 2}]
    world.actor = Actor("extrano")
    assert client.get(f"/api/v1/cases/{case_id}/graph").status_code == 404


def test_mis_casos_no_se_confunde_con_un_id(client: TestClient, world: World) -> None:
    world.points.cases = [
        CaseOnMap(UUID(int=7), "Caso Polanco", "restricted", 8, 3, MIGUEL_HIDALGO)
    ]

    response = client.get("/api/v1/cases/map")

    assert response.status_code == 200
    [item] = response.json()["items"]
    assert (item["sensitivity_label"], item["confirmed_count"]) == ("reservado", 3)
    assert (item["lon"], item["lat"]) == (MIGUEL_HIDALGO.lon, MIGUEL_HIDALGO.lat)
