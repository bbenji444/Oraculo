"""Errores uniformes ante fallas inesperadas y documentación OpenAPI revisada (F5)."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import INTERNAL_ERROR_MESSAGE, error_responses, register_error_handlers
from app.api.v1 import OPENAPI_TAGS
from app.domain.errors import LLMNotConfiguredError
from app.main import create_app


def app_that_fails() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/bug")
    async def bug() -> None:
        raise RuntimeError("detalle interno que no debe salir")

    @app.get("/sin-llave")
    async def no_key() -> None:
        raise LLMNotConfiguredError("Falta la llave de la IA.")

    return app


def test_un_error_inesperado_es_500_uniforme_sin_detalles(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Sin relanzar la excepción: así responde el servidor de verdad.
    client = TestClient(app_that_fails(), raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR):
        response = client.get("/bug")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": INTERNAL_ERROR_MESSAGE, "details": {}}
    }
    assert "detalle interno" not in response.text
    # El detalle sí queda en el registro para depurar.
    assert "Error inesperado en GET /bug" in caplog.text


def test_falta_de_configuracion_es_503() -> None:
    response = TestClient(app_that_fails()).get("/sin-llave")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_not_configured"


def test_cada_ruta_documenta_solo_sus_errores() -> None:
    assert sorted(error_responses()) == [422, 500]
    assert sorted(error_responses(404, 409)) == [404, 409, 422, 500]


def test_openapi_revisado() -> None:
    schema = create_app().openapi()
    known_tags = {t["name"] for t in OPENAPI_TAGS}
    operations = {
        (method.upper(), path): op
        for path, ops in schema["paths"].items()
        for method, op in ops.items()
    }

    for (method, path), op in operations.items():
        assert op.get("summary"), f"{method} {path} sin resumen"
        assert set(op["tags"]) <= known_tags, f"{method} {path} con etiqueta sin describir"
    assert {t["name"] for t in schema["tags"]} == known_tags

    def errors(method: str, path: str) -> list[int]:
        return sorted(int(c) for c in operations[(method, path)]["responses"] if int(c) >= 400)

    assert errors("POST", "/api/v1/searches") == [404, 409, 422, 500, 503]
    assert errors("GET", "/api/v1/regions") == [422, 500]
    assert errors("GET", "/api/v1/articles/{article_id}") == [404, 422, 500]
