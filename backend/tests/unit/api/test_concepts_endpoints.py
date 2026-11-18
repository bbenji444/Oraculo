"""Endpoints /api/v1/concepts con repositorios en memoria (forma de las respuestas y errores)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.v1.concepts import (
    client_ip,
    get_actor,
    get_concept_repository,
    get_preview_providers,
    get_term_suggester,
)
from app.api.v1.regions import get_region_repository
from app.application.audit import Actor
from app.application.use_cases.suggest_terms import SuggestConceptTerms
from app.domain.queries import Provider
from app.main import create_app
from tests.unit.application.test_suggest_terms import INTENT, PRICES, FakeSuggester, result
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import IZTAPALAPA, FakeRegionRepository

URL = "/api/v1/concepts"
BODY: dict[str, Any] = {
    "name": "Ciberseguridad",
    "description": "Ataques informáticos",
    "keywords": ["ciberataque", "hackeo", "ransomware", "filtración de datos", "phishing"],
    "exclude_terms": ["curso", "webinar", "diplomado"],
    "color": "#2e86de",
}


@pytest.fixture
def concepts() -> FakeConceptRepository:
    return FakeConceptRepository()


@pytest.fixture
def client(concepts: FakeConceptRepository) -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_concept_repository] = lambda: concepts
    regions = FakeRegionRepository()
    # Una función sin argumentos: si se pasa la clase, FastAPI tomaría su
    # argumento `regions` como parámetro de la petición.
    app.dependency_overrides[get_region_repository] = lambda: regions
    app.dependency_overrides[get_actor] = lambda: Actor("prueba", "127.0.0.1")
    app.dependency_overrides[get_preview_providers] = lambda: tuple(Provider)
    # Sin `with`: no corre el lifespan, así que no se conecta a la base.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_crear_devuelve_201_con_el_concepto_limpio(client: TestClient) -> None:
    response = client.post(URL, json=BODY)

    assert response.status_code == 201
    body = response.json()
    assert body["color"] == "#2E86DE"
    assert body["created_by"] == "prueba"
    assert body["is_active"] is True


def test_errores_de_validacion_en_espanol_por_campo(client: TestClient) -> None:
    response = client.post(URL, json={**BODY, "keywords": ["Hackeo", "hackéo"], "color": "rojo"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_concept"
    assert [p["campo"] for p in error["details"]["problemas"]] == ["keywords", "color"]


def test_nombre_repetido_es_409(client: TestClient) -> None:
    client.post(URL, json=BODY)

    response = client.post(URL, json={**BODY, "name": "CIBERSEGURIDAD"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "concept_name_taken"


def test_falta_un_campo_obligatorio(client: TestClient) -> None:
    response = client.post(URL, json={"name": "Sin palabras"})

    assert response.status_code == 422
    assert "keywords" in response.json()["error"]["message"]


def test_editar_parcial_y_desactivar(client: TestClient) -> None:
    created = client.post(URL, json=BODY).json()

    response = client.patch(f"{URL}/{created['id']}", json={"is_active": False})

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert response.json()["keywords"] == BODY["keywords"]


def test_listar_solo_activos(client: TestClient) -> None:
    client.post(URL, json=BODY)
    client.post(URL, json={**BODY, "name": "Inactivo", "is_active": False})

    items = client.get(URL, params={"active": "true"}).json()["items"]

    assert [c["name"] for c in items] == ["Ciberseguridad"]


def test_borrar_devuelve_204_y_despues_404(client: TestClient) -> None:
    created = client.post(URL, json=BODY).json()

    assert client.delete(f"{URL}/{created['id']}").status_code == 204
    assert client.get(f"{URL}/{created['id']}").status_code == 404
    assert client.delete(f"{URL}/{created['id']}").json()["error"]["code"] == "concept_not_found"


def test_probar_borrador_sin_guardar(client: TestClient, concepts: FakeConceptRepository) -> None:
    response = client.post(
        f"{URL}/preview", params={"region_id": IZTAPALAPA.id, "days": 7}, json=BODY
    )

    assert response.status_code == 200
    body = response.json()
    assert body["region"]["breadcrumb"] == "México › Ciudad de México › Iztapalapa"
    assert body["window"]["description"] == "últimos 7 días"
    assert [q["provider"] for q in body["queries"]] == [
        "searchapi",
        "searchapi_web",
        "google_news_rss",
        "gdelt",
        "indice_local",
        "browserwork_bing",
        "browserwork_google2",
    ]
    assert body["queries"][0]["provider_label"] == "SearchApi (Google News)"
    assert body["queries"][0]["filters"] == {
        "country": "México",
        "language": "español",
        "period": "últimos 7 días",
    }
    # Google web (ADR-0115) es la segunda consulta de pago: 1 crédito más.
    assert (body["total_queries"], body["total_credits"]) == (7, 2)
    assert concepts.concepts == {}


def test_probar_muestra_solo_los_proveedores_configurados(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_preview_providers] = lambda: (
        Provider.SEARCHAPI,
        Provider.LOCAL_INDEX,
    )

    body = client.post(f"{URL}/preview", params={"region_id": IZTAPALAPA.id}, json=BODY).json()

    assert [q["provider"] for q in body["queries"]] == ["searchapi", "indice_local"]
    assert body["total_queries"] == 2


def test_probar_concepto_guardado(client: TestClient) -> None:
    created = client.post(URL, json=BODY).json()

    body = client.post(f"{URL}/{created['id']}/preview", params={"region_id": IZTAPALAPA.id}).json()

    # Sin ?days= se usa el rango de la historia H1: últimos 7 días.
    assert body["concept_name"] == "Ciberseguridad"
    [rss] = [q for q in body["queries"] if q["provider"] == "google_news_rss"]
    assert rss["text"].endswith("when:7d")


@pytest.mark.parametrize(
    ("params", "code"),
    [({"region_id": 999}, "region_not_found"), ({"region_id": 3, "days": 365}, "invalid_request")],
)
def test_probar_con_region_o_rango_invalidos(
    client: TestClient, params: dict[str, int], code: str
) -> None:
    response = client.post(f"{URL}/preview", params=params, json=BODY)

    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize(
    ("host", "expected"),
    [("127.0.0.1", "127.0.0.1"), ("::1", "::1"), ("testclient", None), (None, None)],
)
def test_la_ip_de_la_bitacora_solo_acepta_ips_validas(
    host: str | None, expected: str | None
) -> None:
    scope: dict[str, Any] = {"type": "http", "client": (host, 50000) if host else None}

    assert client_ip(Request(scope)) == expected


# --- Modo «como en Google» (ADR-0109) ---

OPEN_BODY: dict[str, Any] = {
    "name": "Hackeos",
    "description": "Hackeos y filtraciones de bases de datos en México",
    "keywords": ["filtran datos", "hackeo gobierno"],
    "color": "#2e86de",
    "query_mode": "open",
}


def test_sin_query_mode_la_api_crea_un_concepto_exacto(client: TestClient) -> None:
    # Quien ya usa la API sigue igual; el formulario manda «open».
    body = client.post(URL, json=BODY).json()

    assert (body["query_mode"], body["query_mode_label"]) == ("exact", "frases exactas")


def test_crear_un_concepto_como_en_google(client: TestClient) -> None:
    body = client.post(URL, json=OPEN_BODY).json()

    assert (body["query_mode"], body["query_mode_label"]) == ("open", "como en Google")


def test_cambiar_el_modo_con_patch(client: TestClient) -> None:
    created = client.post(URL, json=BODY).json()

    response = client.patch(f"{URL}/{created['id']}", json={"query_mode": "open"})

    assert response.json()["query_mode"] == "open"


def test_modo_desconocido_es_422(client: TestClient) -> None:
    response = client.post(URL, json={**OPEN_BODY, "query_mode": "libre"})

    assert response.status_code == 422


def test_probar_como_en_google_manda_cada_frase_sola_a_google_news_rss(
    client: TestClient,
) -> None:
    body = client.post(
        f"{URL}/preview", params={"region_id": IZTAPALAPA.id, "days": 7}, json=OPEN_BODY
    ).json()

    rss = [q["text"] for q in body["queries"] if q["provider"] == "google_news_rss"]
    assert rss == [
        "filtran datos Iztapalapa when:7d",
        "hackeo gobierno Iztapalapa when:7d",
    ]


# --- La IA propone las frases (ADR-0109) ---


def test_proponer_frases_devuelve_la_propuesta_limpia(
    client: TestClient, concepts: FakeConceptRepository
) -> None:
    suggester = FakeSuggester(
        result("filtran datos", "Filtran datos", "hackeo gobierno", excludes=("curso",))
    )
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_term_suggester] = lambda: SuggestConceptTerms(
        suggester, PRICES, concepts
    )

    response = client.post(f"{URL}/suggest", json={"description": INTENT})

    assert response.status_code == 200
    assert response.json() == {
        "name": "Hackeos a gobierno",
        "keywords": ["filtran datos", "hackeo gobierno"],
        "exclude_terms": ["curso"],
        "query_mode": "open",
        "model": "gpt-6-luna",
        "cost_usd": 0.002,
    }
    # No se guardó ningún concepto: solo la bitácora.
    assert concepts.concepts == {}
    assert [entry.action for _, entry in concepts.audit] == ["concept.terms_suggested"]


def test_proponer_con_descripcion_corta_es_422_por_campo(
    client: TestClient, concepts: FakeConceptRepository
) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_term_suggester] = lambda: SuggestConceptTerms(
        FakeSuggester(result("filtran datos")), PRICES, concepts
    )

    response = client.post(f"{URL}/suggest", json={"description": "robo"})

    assert response.status_code == 422
    problems = response.json()["error"]["details"]["problemas"]
    assert [p["campo"] for p in problems] == ["description"]


def test_proponer_sin_ia_configurada_es_503(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.term_suggester = None

    response = client.post(f"{URL}/suggest", json={"description": INTENT})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_not_configured"
