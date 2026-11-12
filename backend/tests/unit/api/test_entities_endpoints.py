"""Endpoints de las entidades de un caso con repositorios en memoria (Fase 9.4)."""

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.cases import get_case_repository, get_on_article_added
from app.api.v1.concepts import get_actor
from app.api.v1.entities import get_entity_repository, get_extraction_queue, get_llm_prices
from app.application.audit import Actor
from app.application.use_cases.entities import QueueExtraction
from app.application.use_cases.reports import LLMPrices
from app.domain.entity_extraction import CaseArticleEntitiesStatus
from app.domain.investigation import CaseMemberRole
from app.main import create_app
from tests.unit.application.test_entities_use_cases import person
from tests.unit.fake_cases import FakeCaseRepository
from tests.unit.fake_entities import FakeEntityQueue, FakeEntityRepository


class World:
    """Repositorios, cola y quién pide (las pruebas cambian al usuario)."""

    def __init__(self) -> None:
        self.cases = FakeCaseRepository()
        self.entities = FakeEntityRepository()
        self.queue = FakeEntityQueue()
        self.actor = Actor("benji", "127.0.0.1")


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    app: FastAPI = create_app()
    queuer = QueueExtraction(world.entities, world.queue)
    app.dependency_overrides[get_case_repository] = lambda: world.cases
    app.dependency_overrides[get_entity_repository] = lambda: world.entities
    app.dependency_overrides[get_extraction_queue] = lambda: queuer
    app.dependency_overrides[get_on_article_added] = lambda: queuer
    app.dependency_overrides[get_llm_prices] = lambda: LLMPrices("openai", 0.10, 0.50)
    app.dependency_overrides[get_actor] = lambda: world.actor
    yield TestClient(app)
    app.dependency_overrides.clear()


def new_case(client: TestClient, world: World) -> UUID:
    case_id = UUID(client.post("/api/v1/cases", json={"name": "Caso Polanco"}).json()["id"])
    world.cases.add_member(case_id, "lectora", CaseMemberRole.VIEWER)
    return case_id


def test_agregar_una_nota_la_encola_para_la_ia(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    world.cases.articles[7] = object()  # type: ignore[assignment]  # solo importa que exista
    world.entities.add_article(case_id, 7)

    response = client.post(f"/api/v1/cases/{case_id}/articles", json={"article_id": 7})

    assert response.json() == {"article_id": 7, "added": True}
    assert world.queue.queued == [(case_id, 7, "benji")]
    assert world.entities.status_of(case_id, 7) is CaseArticleEntitiesStatus.QUEUED


def test_listar_trae_etiquetas_evidencia_y_avance(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    world.entities.add_entity(case_id, person(1, mentions=2))
    world.entities.add_article(case_id, 5)

    body = client.get(f"/api/v1/cases/{case_id}/entities").json()

    [item] = body["items"]
    assert (item["type_label"], item["review_status_label"]) == ("persona", "sugerido")
    assert item["suggested_legal_status_label"] == "detenido"
    assert item["mentions"][0]["evidence_span"] == "orden de aprehensión"
    assert body["counts"] == {"suggested": 1, "confirmed": 0, "discarded": 0}
    assert body["analysis"]["pending"] == 1
    assert body["analysis"]["estimated_pending_cost_usd"] > 0


def test_analizar_pendientes_encola_y_responde_el_estimado(
    client: TestClient, world: World
) -> None:
    case_id = new_case(client, world)
    world.entities.add_article(case_id, 5)

    response = client.post(f"/api/v1/cases/{case_id}/extract")

    assert response.status_code == 200
    assert response.json()["queued"] == 1
    world.actor = Actor("lectora")
    assert client.post(f"/api/v1/cases/{case_id}/extract").status_code == 403


def test_confirmar_y_descartar(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    world.entities.add_entity(case_id, person(1))
    world.entities.add_entity(case_id, person(2))
    url = "/api/v1/entities"

    missing = client.post(f"{url}/1/confirm", json={"case_id": str(case_id)})
    guilty = client.post(
        f"{url}/1/confirm", json={"case_id": str(case_id), "legal_status": "culpable"}
    )
    confirmed = client.post(
        f"{url}/1/confirm", json={"case_id": str(case_id), "legal_status": "alleged"}
    )
    discarded = client.post(f"{url}/2/discard", json={"case_id": str(case_id)})

    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "invalid_entity_review"
    assert guilty.status_code == 422
    assert confirmed.json()["legal_status_label"] == "señalado"
    assert confirmed.json()["reviewed_by"] == "benji"
    assert discarded.json()["review_status"] == "discarded"
    assert client.post(f"{url}/9/discard", json={"case_id": str(case_id)}).status_code == 404


def test_revisar_en_bloque(client: TestClient, world: World) -> None:
    case_id = new_case(client, world)
    for entity_id in (1, 2, 3):
        world.entities.add_entity(case_id, person(entity_id))
    url = f"/api/v1/cases/{case_id}/entities/review"

    confirmed = client.post(
        url,
        json={
            "action": "confirm",
            "items": [
                {"entity_id": 1, "legal_status": "alleged"},
                {"entity_id": 2, "legal_status": "victim"},
            ],
        },
    )
    discarded = client.post(url, json={"action": "discard", "items": [{"entity_id": 3}]})
    without_status = client.post(url, json={"action": "confirm", "items": [{"entity_id": 3}]})
    empty = client.post(url, json={"action": "discard", "items": []})
    missing = client.post(url, json={"action": "discard", "items": [{"entity_id": 9}]})

    assert confirmed.json() == {"changed": 2, "unchanged": 0}
    assert discarded.json() == {"changed": 1, "unchanged": 0}
    assert without_status.json()["error"]["code"] == "invalid_entity_review"
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "invalid_bulk_review"
    assert missing.status_code == 404
    counts = client.get(f"/api/v1/cases/{case_id}/entities").json()["counts"]
    assert counts == {"suggested": 0, "confirmed": 2, "discarded": 1}
    world.actor = Actor("lectora")
    assert (
        client.post(url, json={"action": "discard", "items": [{"entity_id": 1}]}).status_code == 403
    )
