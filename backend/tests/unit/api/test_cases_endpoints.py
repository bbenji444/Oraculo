"""Endpoints /api/v1/cases con un repositorio en memoria y dos personas (Fase 9.3).

Cada ruta se recorre también con una segunda persona sin acceso: un caso
ajeno debe responder igual que uno que no existe (404), nunca 403.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.cases import get_case_repository
from app.api.v1.concepts import get_actor
from app.application.audit import Actor
from app.domain.investigation import CaseMemberRole, InvestigationAction
from app.main import create_app
from tests.unit.fake_cases import FakeCaseRepository

URL = "/api/v1/cases"
BODY: dict[str, Any] = {
    "name": "Homicidio estilista Polanco",
    "description": "Caso Micky Hair",
    "sensitivity": "restricted",
}


class Session:
    """Quién hace la petición; las pruebas lo cambian para simular a otra persona."""

    def __init__(self) -> None:
        self.actor = Actor("benji", "127.0.0.1")

    def as_user(self, user: str) -> None:
        self.actor = Actor(user, "127.0.0.1")


@pytest.fixture
def repo() -> FakeCaseRepository:
    return FakeCaseRepository()


@pytest.fixture
def session() -> Session:
    return Session()


@pytest.fixture
def client(repo: FakeCaseRepository, session: Session) -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_case_repository] = lambda: repo
    app.dependency_overrides[get_actor] = lambda: session.actor
    # Sin `with`: no corre el lifespan, así que no se conecta a la base.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_crear_devuelve_201_con_etiquetas_y_rol_de_dueno(client: TestClient) -> None:
    response = client.post(URL, json=BODY)

    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["status"], body["status_label"]) == (
        "Homicidio estilista Polanco",
        "open",
        "abierto",
    )
    assert (body["sensitivity"], body["sensitivity_label"], body["role"]) == (
        "restricted",
        "reservado",
        "owner",
    )
    assert body["article_count"] == 0


def test_datos_invalidos_responden_422_por_campo(client: TestClient) -> None:
    response = client.post(URL, json={"name": " ", "sensitivity": "secreto"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_case"
    assert [p["campo"] for p in error["details"]["problemas"]] == ["name", "sensitivity"]


def test_abrir_un_caso_queda_en_la_bitacora(client: TestClient, repo: FakeCaseRepository) -> None:
    case_id = client.post(URL, json=BODY).json()["id"]

    response = client.get(f"{URL}/{case_id}")

    assert response.status_code == 200
    assert response.json()["role"] == "owner"
    assert [e.action for _, e, _ in repo.audit] == [
        InvestigationAction.CASE_CREATED,
        InvestigationAction.CASE_VIEWED,
    ]


def test_un_caso_ajeno_responde_igual_que_uno_inexistente(
    client: TestClient, session: Session
) -> None:
    case_id = client.post(URL, json=BODY).json()["id"]
    session.as_user("otra-analista")

    ajeno = client.get(f"{URL}/{case_id}")
    inexistente = client.get(f"{URL}/00000000-0000-0000-0000-000000000000")
    editar = client.patch(f"{URL}/{case_id}", json={"name": "Robado"})

    assert ajeno.status_code == inexistente.status_code == editar.status_code == 404
    assert ajeno.json()["error"] == {
        **inexistente.json()["error"],
        "details": {"id": case_id},
    }
    assert client.get(URL).json() == {"items": [], "next_cursor": None}


def test_un_lector_no_edita_y_recibe_403(
    client: TestClient, repo: FakeCaseRepository, session: Session
) -> None:
    case_id = client.post(URL, json=BODY).json()["id"]
    repo.add_member(next(iter(repo.cases)), "lectora", CaseMemberRole.VIEWER)
    session.as_user("lectora")

    response = client.patch(f"{URL}/{case_id}", json={"name": "Otro"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "case_forbidden"
    assert client.get(f"{URL}/{case_id}").json()["role"] == "viewer"


def test_cerrar_un_caso_y_luego_no_poder_editar_sus_datos(client: TestClient) -> None:
    case_id = client.post(URL, json=BODY).json()["id"]

    closed = client.patch(f"{URL}/{case_id}", json={"status": "closed"}).json()
    blocked = client.patch(f"{URL}/{case_id}", json={"name": "Otro"})

    assert (closed["status_label"], closed["closed_at"] is not None) == ("cerrado", True)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "case_closed"


def test_la_lista_filtra_por_estado_y_dice_si_tiene_la_nota(client: TestClient) -> None:
    client.post(URL, json=BODY)
    archived = client.post(URL, json={**BODY, "name": "Viejo"}).json()["id"]
    client.patch(f"{URL}/{archived}", json={"status": "archived"})

    default = client.get(URL, params={"contains_article": 7}).json()["items"]
    only_archived = client.get(URL, params={"status": "archived"}).json()["items"]

    assert [(c["name"], c["has_article"]) for c in default] == [
        ("Homicidio estilista Polanco", False)
    ]
    assert [c["name"] for c in only_archived] == ["Viejo"]
    assert client.get(URL, params={"status": "borrado"}).status_code == 422


def test_agregar_listar_y_quitar_notas(client: TestClient, repo: FakeCaseRepository) -> None:
    case_id = client.post(URL, json=BODY).json()["id"]
    repo.known_article(10, "Micky Hair: qué se sabe", None)

    added = client.post(f"{URL}/{case_id}/articles", json={"article_id": 10})
    again = client.post(f"{URL}/{case_id}/articles", json={"article_id": 10})
    listed = client.get(f"{URL}/{case_id}/articles").json()
    removed = client.delete(f"{URL}/{case_id}/articles/10")

    assert (added.status_code, added.json()) == (200, {"article_id": 10, "added": True})
    assert again.json()["added"] is False
    assert [a["title"] for a in listed["items"]] == ["Micky Hair: qué se sabe"]
    assert removed.status_code == 204
    assert client.get(f"{URL}/{case_id}/articles").json()["items"] == []


def test_agregar_una_nota_inexistente_responde_404(client: TestClient) -> None:
    case_id = client.post(URL, json=BODY).json()["id"]

    response = client.post(f"{URL}/{case_id}/articles", json={"article_id": 999})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "article_not_found"


def test_las_notas_de_un_caso_ajeno_no_existen(
    client: TestClient, repo: FakeCaseRepository, session: Session
) -> None:
    case_id = client.post(URL, json=BODY).json()["id"]
    repo.known_article(10, "Nota", None)
    session.as_user("otra-analista")

    responses = [
        client.get(f"{URL}/{case_id}/articles"),
        client.post(f"{URL}/{case_id}/articles", json={"article_id": 10}),
        client.delete(f"{URL}/{case_id}/articles/10"),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404]
