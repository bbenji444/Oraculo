"""Endpoint GET /api/v1/health con el caso de uso reemplazado por uno falso.

TestClient se usa sin ``with`` a propósito: así no corre el ``lifespan`` y no
se intenta conectar a PostgreSQL, Redis ni Celery.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.health import get_check_health
from app.application.use_cases.check_health import CheckSystemHealth
from app.domain.health import ComponentHealth
from app.main import create_app


class StaticProbe:
    def __init__(self, result: ComponentHealth) -> None:
        self.name = result.name
        self._result = result

    async def check(self) -> ComponentHealth:
        return self._result


@pytest.fixture
def app() -> Iterator[FastAPI]:
    application = create_app()
    yield application
    application.dependency_overrides.clear()


def use_probes(app: FastAPI, *results: ComponentHealth) -> TestClient:
    use_case = CheckSystemHealth([StaticProbe(r) for r in results], timeout_seconds=1)
    app.dependency_overrides[get_check_health] = lambda: use_case
    return TestClient(app)


def test_todo_ok_responde_200_con_cada_componente(app: FastAPI) -> None:
    client = use_probes(
        app,
        ComponentHealth.ok("api", info={"version": "0.0.0"}),
        ComponentHealth.ok("database", info={"postgis": "3.6"}),
    )

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [c["name"] for c in body["components"]] == ["api", "database"]
    assert body["components"][1]["info"] == {"postgis": "3.6"}
    assert body["components"][0]["latency_ms"] is not None


def test_un_componente_con_error_responde_503_y_explica_que_fallo(app: FastAPI) -> None:
    client = use_probes(
        app,
        ComponentHealth.ok("api"),
        ComponentHealth.error("redis", "No se pudo conectar a Redis (ConnectionError)."),
    )

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"][1] == {
        "name": "redis",
        "status": "error",
        "detail": "No se pudo conectar a Redis (ConnectionError).",
        "latency_ms": body["components"][1]["latency_ms"],
        "info": {},
    }


def test_el_endpoint_aparece_en_openapi(app: FastAPI) -> None:
    schema = TestClient(app).get("/api/v1/openapi.json").json()

    assert "/api/v1/health" in schema["paths"]
