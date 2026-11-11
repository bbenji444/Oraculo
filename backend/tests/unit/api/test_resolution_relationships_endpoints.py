"""Endpoints de duplicados y vínculos de un caso con repositorios en memoria (Fase 9.5)."""

from collections.abc import Iterator
from dataclasses import replace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.cases import get_case_repository
from app.api.v1.concepts import get_actor
from app.api.v1.entities import get_entity_repository
from app.api.v1.relationships import get_relationship_repository
from app.application.audit import Actor
from app.application.ports.entities import CaseEntity, MergeSuggestion
from app.application.ports.relationships import SharedArticle
from app.domain.entity_resolution import MergeReason
from app.domain.investigation import CaseMemberRole, LegalStatus, ReviewStatus
from app.main import create_app
from tests.unit.application.test_entities_use_cases import person
from tests.unit.fake_cases import FakeCaseRepository
from tests.unit.fake_entities import FakeEntityRepository
from tests.unit.fake_relationships import FakeRelationshipRepository, suggested


class World:
    """Repositorios y quién pide (las pruebas cambian al usuario)."""

    def __init__(self) -> None:
        self.cases = FakeCaseRepository()
        self.entities = FakeEntityRepository()
        self.relationships = FakeRelationshipRepository()
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
    app.dependency_overrides[get_actor] = lambda: world.actor
    yield TestClient(app)
    app.dependency_overrides.clear()


def new_case(client: TestClient, world: World) -> UUID:
    case_id = UUID(client.post("/api/v1/cases", json={"name": "Caso Polanco"}).json()["id"])
    world.cases.add_member(case_id, "lectora", CaseMemberRole.VIEWER)
    return case_id


def confirmed(entity_id: int) -> CaseEntity:
    return replace(
        person(entity_id), review_status=ReviewStatus.CONFIRMED, legal_status=LegalStatus.ALLEGED
    )


def test_duplicados_lado_a_lado_con_su_motivo(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    one, two = person(1, mentions=1), person(2, mentions=3)
    world.entities.add_entity(case_id, one)
    world.entities.add_entity(case_id, two)
    world.entities.suggestions = [
        MergeSuggestion(one, two, frozenset({MergeReason.SHARED_NAME, MergeReason.SIMILAR_NAME}))
    ]

    body = client.get(f"/api/v1/cases/{case_id}/merge-suggestions").json()

    [item] = body["items"]
    assert (item["reason"], item["reason_label"]) == ("shared_name", "nombre o alias en común")
    assert item["reasons"] == ["shared_name", "similar_name"]
    assert item["keep_id"] == 2
    assert item["second"]["mentions"][0]["id"] == 0
    assert item["second"]["mentions"][0]["entity_id"] == 2


def test_unir_separar_y_no_son_la_misma(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    for entity_id in (1, 2, 3):
        world.entities.add_entity(case_id, person(entity_id))
    case = {"case_id": str(case_id)}

    merged = client.post("/api/v1/entities/merge", json={**case, "keep_id": 1, "merge_id": 2})
    again = client.post("/api/v1/entities/merge", json={**case, "keep_id": 3, "merge_id": 2})
    unmerged = client.post("/api/v1/entities/2/unmerge", json=case)
    dismissed = client.post(
        "/api/v1/entities/merge/dismiss", json={**case, "first_id": 3, "second_id": 1}
    )
    split = client.post("/api/v1/entities/1/split", json={**case, "mention_ids": [1]})
    empty = client.post("/api/v1/entities/1/split", json={**case, "mention_ids": []})

    assert merged.status_code == 200
    assert merged.json()["merged"] == [{"id": 2, "label": "Persona 2", "merged_into": 1}]
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "invalid_entity_merge"
    assert unmerged.json()["id"] == 2
    assert dismissed.json() == {"dismissed": True}
    assert split.json()["review_status"] == "suggested"
    assert empty.status_code == 422


def test_un_lector_mira_pero_no_une(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    world.entities.add_entity(case_id, person(1))
    world.entities.add_entity(case_id, person(2))
    world.actor = Actor("lectora")

    listed = client.get(f"/api/v1/cases/{case_id}/merge-suggestions")
    merged = client.post(
        "/api/v1/entities/merge", json={"case_id": str(case_id), "keep_id": 1, "merge_id": 2}
    )

    assert listed.status_code == 200
    assert merged.status_code == 403


def test_vinculos_listar_confirmar_y_dibujar(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    for entity_id in (1, 2, 3):
        world.entities.add_entity(case_id, confirmed(entity_id))
    world.relationships.views[case_id] = [suggested(1, 2, shared=2)]
    case = {"case_id": str(case_id)}

    listed = client.get(f"/api/v1/cases/{case_id}/relationships").json()
    confirm = client.post(
        "/api/v1/relationships/confirm",
        json={**case, "entity_a": 1, "entity_b": 2, "type": "appears_with"},
    )
    missing = client.post(
        "/api/v1/relationships/discard",
        json={**case, "entity_a": 1, "entity_b": 3, "type": "appears_with"},
    )
    drawn = client.post(
        "/api/v1/relationships",
        json={**case, "entity_a": 3, "entity_b": 1, "type": "custom", "custom_label": "socio"},
    )
    no_label = client.post(
        "/api/v1/relationships", json={**case, "entity_a": 3, "entity_b": 1, "type": "custom"}
    )

    [item] = listed["items"]
    assert item["id"] is None
    assert (item["type_label"], item["origin_label"]) == (
        "aparecen juntas",
        "aparecen en la misma nota",
    )
    assert (item["confidence"], item["symmetric"]) == (0.7, True)
    assert item["entity_a"]["legal_status_label"] == "señalado"
    assert confirm.json()["review_status"] == "confirmed"
    assert confirm.json()["reviewed_by"] == "benji"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "relationship_not_found"
    assert drawn.status_code == 200
    assert (drawn.json()["origin"], drawn.json()["confidence"]) == ("human", 1.0)
    assert (drawn.json()["entity_a"]["id"], drawn.json()["custom_label"]) == (3, "socio")
    assert no_label.status_code == 422
    assert no_label.json()["error"]["code"] == "invalid_relationship"


def test_vinculos_revisar_en_bloque(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    for entity_id in (1, 2, 3):
        world.entities.add_entity(case_id, confirmed(entity_id))
    world.relationships.views[case_id] = [suggested(1, 2), suggested(1, 3)]
    url = f"/api/v1/cases/{case_id}/relationships/review"
    pair = {"entity_a": 1, "entity_b": 2, "type": "appears_with"}

    discarded = client.post(
        url,
        json={
            "action": "discard",
            "items": [pair, {"entity_a": 1, "entity_b": 3, "type": "appears_with"}],
        },
    )
    missing = client.post(
        url,
        json={"action": "confirm", "items": [{"entity_a": 2, "entity_b": 3, "type": "family"}]},
    )
    wrong = client.post(url, json={"action": "suggest", "items": [pair]})

    assert discarded.json() == {"changed": 2, "unchanged": 0}
    counts = client.get(f"/api/v1/cases/{case_id}/relationships").json()["counts"]
    assert counts == {"suggested": 0, "confirmed": 0, "discarded": 2}
    assert missing.status_code == 404
    assert wrong.status_code == 422


def test_vinculos_traen_su_fuerza_y_su_razon(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    for entity_id in (1, 2, 3):
        world.entities.add_entity(case_id, confirmed(entity_id))
    shared = SharedArticle(10, "Nota 10", "https://medio.mx/10", None, same_event=True)
    world.relationships.views[case_id] = [
        suggested(1, 2),
        replace(suggested(1, 3), shared_articles=(shared,)),
    ]

    strong, weak = client.get(f"/api/v1/cases/{case_id}/relationships").json()["items"]

    assert (strong["entity_b"]["id"], strong["strength"], strong["same_event_count"]) == (
        3,
        "strong",
        1,
    )
    assert strong["strength_label"] == "relación fuerte"
    assert strong["reason"] == "participan en el mismo hecho en 1 nota"
    assert strong["shared_articles"][0]["same_event"] is True
    assert (weak["strength"], weak["strength_label"]) == ("weak", "solo se mencionan juntas")
