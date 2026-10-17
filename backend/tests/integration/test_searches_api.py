"""Endpoints de búsquedas de punta a punta: HTTP → casos de uso → PostgreSQL.

Arranca la aplicación real contra la base de pruebas con el mini-catálogo.
La cola del worker es falsa: ninguna prueba corre una búsqueda de verdad ni
gasta créditos.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text

from app.api.v1.searches import get_search_queue
from app.core.config import Settings
from app.main import create_app
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
URL = "/api/v1/searches"
CONCEPT_NAME = "Prueba API búsquedas"


class FakeQueue:
    def __init__(self) -> None:
        self.sent: list[UUID] = []

    def enqueue(self, search_id: UUID) -> None:
        self.sent.append(search_id)


def _clean(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM searches"))
        conn.execute(text("DELETE FROM articles"))
        conn.execute(text("DELETE FROM audit_log WHERE entity_type = 'search'"))
        conn.execute(text("DELETE FROM concepts WHERE name LIKE 'Prueba API%'"))


@pytest.fixture(scope="module")
def engine(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    sync_engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(sync_engine, settings, tmp_path_factory.mktemp("geodata"))
    yield sync_engine
    _clean(sync_engine)
    sync_engine.dispose()


@pytest.fixture
def ids(engine: Engine) -> Iterator[dict[str, int]]:
    _clean(engine)
    with engine.begin() as conn:
        concept = conn.execute(
            text(
                "INSERT INTO concepts (name, name_norm, description, keywords, exclude_terms, "
                "color, created_by) VALUES (:n, 'PRUEBA API BUSQUEDAS', 'Cobro de piso', "
                "'{extorsión}', '{simulacro}', '#AA0000', 'prueba') RETURNING id"
            ),
            {"n": CONCEPT_NAME},
        ).scalar_one()
        off = conn.execute(
            text(
                "INSERT INTO concepts (name, name_norm, keywords, color, created_by, is_active) "
                "VALUES ('Prueba API apagado', 'PRUEBA API APAGADO', '{robo}', '#00AA00', "
                "'prueba', false) RETURNING id"
            )
        ).scalar_one()
        cdmx = conn.execute(text("SELECT id FROM regions WHERE code = '09'")).scalar_one()
    yield {"concept": concept, "off": off, "cdmx": cdmx}
    _clean(engine)


def make_client(settings: Settings, queue: FakeQueue, **changes: Any) -> TestClient:
    test_settings = settings.model_copy(
        update={
            "postgres_db": settings.postgres_test_db,
            "dev_user": "analista-prueba",
            # Con llave, SearchApi se planea (1 crédito); la cola falsa nunca lo consulta.
            "searchapi_api_key": SecretStr("llave-de-prueba"),
            "openai_api_key": SecretStr("llave-de-prueba"),
            "llm_provider": "openai",
            **changes,
        }
    )
    app = create_app(test_settings)
    app.dependency_overrides[get_search_queue] = lambda: queue
    return TestClient(app)


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
def client(settings: Settings, engine: Engine, queue: FakeQueue) -> Iterator[TestClient]:
    with make_client(settings, queue) as test_client:
        yield test_client


def body(ids: dict[str, int], **changes: Any) -> dict[str, Any]:
    return {"concept_ids": [ids["concept"]], "region_id": ids["cdmx"], "days": 7, **changes}


def test_estimar_no_crea_nada_y_dice_cuanto_costaria(
    client: TestClient, ids: dict[str, int], engine: Engine, queue: FakeQueue
) -> None:
    response = client.post(f"{URL}/estimate", json=body(ids))

    assert response.status_code == 200
    data = response.json()
    assert [c["name"] for c in data["concepts"]] == [CONCEPT_NAME]
    assert data["region"] == "México › Ciudad de México"
    assert [q["provider"] for q in data["queries"]] == ["searchapi", "indice_local"]
    assert data["credits"] == 1
    assert data["over_limit"] is False
    assert data["llm"] == {
        "provider": "openai",
        "model": "gpt-6-luna",
        "configured": True,
        "max_articles": 150,
        "max_cost_usd": 0.0525,
    }
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM searches")).scalar_one() == 0
    assert queue.sent == []


def test_lanzar_crea_la_busqueda_pendiente_y_la_encola(
    client: TestClient, ids: dict[str, int], engine: Engine, queue: FakeQueue
) -> None:
    response = client.post(URL, json=body(ids, date_from="2026-10-01", date_to="2026-10-07"))

    assert response.status_code == 202
    data = response.json()
    search_id = UUID(data["search_id"])
    assert data["status"] == "pending"
    assert queue.sent == [search_id]
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT s.user_id, s.status, s.date_from::text, s.date_to::text, "
                    "s.queries_planned, s.credits_estimated, sc.concept_name, sc.exclude_terms "
                    "FROM searches s JOIN search_concepts sc ON sc.search_id = s.id "
                    "WHERE s.id = :id"
                ),
                {"id": search_id},
            )
            .mappings()
            .one()
        )
    assert dict(row) == {
        "user_id": "analista-prueba",
        "status": "pending",
        "date_from": "2026-10-01",
        "date_to": "2026-10-07",
        "queries_planned": 2,
        "credits_estimated": 1,
        "concept_name": CONCEPT_NAME,
        "exclude_terms": ["simulacro"],
    }


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"concept_ids": []}, (422, "invalid_request")),
        ({"concept_ids": [999999]}, (404, "concept_not_found")),
        ({"region_id": 999999}, (404, "region_not_found")),
        ({"days": 120}, (422, "invalid_request")),
        ({"date_from": "2026-10-01"}, (422, "invalid_request")),
        ({"date_from": "2026-10-07", "date_to": "2026-10-01"}, (422, "invalid_request")),
    ],
)
def test_peticiones_invalidas_no_crean_nada(
    client: TestClient,
    ids: dict[str, int],
    queue: FakeQueue,
    changes: dict[str, Any],
    expected: tuple[int, str],
) -> None:
    response = client.post(URL, json=body(ids, **changes))

    assert (response.status_code, response.json()["error"]["code"]) == expected
    assert queue.sent == []


def test_concepto_desactivado_se_rechaza(client: TestClient, ids: dict[str, int]) -> None:
    response = client.post(f"{URL}/estimate", json=body(ids, concept_ids=[ids["off"]]))

    assert response.status_code == 422
    assert "desactivado" in response.json()["error"]["message"]


def test_sin_llave_de_la_ia_es_503_y_con_tope_es_409(
    settings: Settings, engine: Engine, ids: dict[str, int]
) -> None:
    queue = FakeQueue()
    with make_client(settings, queue, openai_api_key=None) as no_key:
        estimate = no_key.post(f"{URL}/estimate", json=body(ids))
        missing = no_key.post(URL, json=body(ids))
    with make_client(settings, queue, searchapi_monthly_credit_limit=0) as capped:
        over = capped.post(URL, json=body(ids))

    # Estimar sí se puede sin llave: avisa que no está configurada.
    assert estimate.status_code == 200
    assert estimate.json()["llm"]["configured"] is False
    assert (missing.status_code, missing.json()["error"]["code"]) == (503, "llm_not_configured")
    assert (over.status_code, over.json()["error"]["code"]) == (409, "credit_limit_reached")
    assert over.json()["error"]["details"] == {"creditos": 1, "usados_en_el_mes": 0, "tope": 0}
    assert queue.sent == []
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM searches")).scalar_one() == 0


def test_detalle_e_historial_con_cursor(client: TestClient, ids: dict[str, int]) -> None:
    created = [client.post(URL, json=body(ids)).json()["search_id"] for _ in range(3)]

    detail = client.get(f"{URL}/{created[0]}")
    first = client.get(URL, params={"limit": 2})
    second = client.get(URL, params={"limit": 2, "cursor": first.json()["next_cursor"]})

    assert detail.status_code == 200
    data = detail.json()
    assert (data["status"], data["region_name"], data["region_code"]) == (
        "pending",
        "Ciudad de México",
        "09",
    )
    assert data["concepts"] == [{"id": ids["concept"], "name": CONCEPT_NAME}]
    assert (data["credits_estimated"], data["credits_used"], data["progress"]) == (1, 0, {})
    # La más reciente primero; la segunda página trae la que falta.
    assert [s["search_id"] for s in first.json()["items"]] == created[:0:-1]
    assert [s["search_id"] for s in second.json()["items"]] == created[:1]
    assert second.json()["next_cursor"] is None


@pytest.mark.parametrize(
    ("path", "params", "expected"),
    [
        ("/00000000-0000-0000-0000-000000000000", {}, (404, "search_not_found")),
        ("/no-es-un-uuid", {}, (422, "invalid_request")),
        ("", {"cursor": "dañado"}, (422, "invalid_request")),
        ("", {"limit": 0}, (422, "invalid_request")),
    ],
)
def test_lecturas_invalidas(
    client: TestClient, path: str, params: dict[str, Any], expected: tuple[int, str]
) -> None:
    response = client.get(URL + path, params=params)

    assert (response.status_code, response.json()["error"]["code"]) == expected
