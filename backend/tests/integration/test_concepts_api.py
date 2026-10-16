"""CRUD de conceptos de punta a punta: HTTP → caso de uso → PostgreSQL → bitácora.

Arranca la aplicación real (con su lifespan) contra la base de pruebas con el
mini-catálogo geográfico, como un analista que usa la pantalla de conceptos.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from app.core.config import Settings
from app.main import create_app
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
URL = "/api/v1/concepts"
BODY: dict[str, Any] = {
    "name": "Ciberseguridad",
    "description": "Ataques informáticos, robo de datos y fraudes digitales",
    "keywords": ["ciberataque", "hackeo", "ransomware", "filtración de datos", "phishing"],
    "exclude_terms": ["curso", "webinar", "diplomado"],
    "color": "#2E86DE",
}


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM concepts"))
        conn.execute(text("DELETE FROM audit_log"))


@pytest.fixture(scope="module")
def engine(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    sync_engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(sync_engine, settings, tmp_path_factory.mktemp("geodata"))
    yield sync_engine
    _empty(sync_engine)
    sync_engine.dispose()


@pytest.fixture(scope="module")
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    test_settings = settings.model_copy(
        update={"postgres_db": settings.postgres_test_db, "dev_user": "analista-prueba"}
    )
    with TestClient(create_app(test_settings)) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean(engine: Engine) -> None:
    _empty(engine)


def region_id(engine: Engine, code: str) -> int:
    with engine.connect() as conn:
        found: int = conn.execute(
            text("SELECT id FROM regions WHERE code = :c"), {"c": code}
        ).scalar_one()
        return found


def audit(engine: Engine) -> list[tuple[str, str, str]]:
    with engine.connect() as conn:
        return [
            (r.action, r.user_id, r.changed)
            for r in conn.execute(
                text(
                    "SELECT action, user_id, COALESCE(payload->>'changed', '') AS changed "
                    "FROM audit_log ORDER BY id"
                )
            )
        ]


def test_crud_completo_con_bitacora(client: TestClient, engine: Engine) -> None:
    # Crear.
    created = client.post(URL, json=BODY)
    assert created.status_code == 201, created.text
    concept_id = created.json()["id"]

    # Nombre repetido (sin importar mayúsculas ni acentos).
    clash = client.post(URL, json={**BODY, "name": "CIBERSEGURIDAD"})
    assert clash.status_code == 409
    assert "Ya existe un concepto" in clash.json()["error"]["message"]

    # Editar: agregar una palabra clave.
    edited = client.patch(
        f"{URL}/{concept_id}", json={"keywords": [*BODY["keywords"], "robo de datos"]}
    )
    assert edited.status_code == 200
    assert edited.json()["keywords"][-1] == "robo de datos"

    # Desactivar: sigue en la lista general, ya no en la de activos.
    client.patch(f"{URL}/{concept_id}", json={"is_active": False})
    assert [c["id"] for c in client.get(URL).json()["items"]] == [concept_id]
    assert client.get(URL, params={"active": "true"}).json()["items"] == []

    # Borrar: el nombre queda libre.
    assert client.delete(f"{URL}/{concept_id}").status_code == 204
    assert client.get(f"{URL}/{concept_id}").status_code == 404
    assert client.post(URL, json=BODY).status_code == 201

    assert audit(engine) == [
        ("concept.created", "analista-prueba", ""),
        ("concept.updated", "analista-prueba", '["keywords"]'),
        ("concept.updated", "analista-prueba", '["is_active"]'),
        ("concept.deleted", "analista-prueba", ""),
        ("concept.created", "analista-prueba", ""),
    ]


def test_lista_paginada_no_repite_ni_salta(client: TestClient) -> None:
    names = ["Secuestro", "Extorsión", "Ciberseguridad", "Robo de vehículos", "Abigeato"]
    for name in names:
        assert client.post(URL, json={**BODY, "name": name}).status_code == 201

    seen: list[str] = []
    params: dict[str, Any] = {"limit": 2}
    while True:
        page = client.get(URL, params=params).json()
        seen.extend(c["name"] for c in page["items"])
        if page["next_cursor"] is None:
            break
        params["cursor"] = page["next_cursor"]

    assert seen == sorted(names, key=lambda n: n.replace("ó", "o"))


def test_vista_previa_del_caso_de_la_especificacion(client: TestClient, engine: Engine) -> None:
    concept_id = client.post(URL, json=BODY).json()["id"]

    body = client.post(
        f"{URL}/{concept_id}/preview", params={"region_id": region_id(engine, "09007"), "days": 7}
    ).json()

    base = (
        '(ciberataque OR hackeo OR ransomware OR "filtración de datos" OR phishing) '
        "Iztapalapa -curso -webinar -diplomado"
    )
    assert [q["text"] for q in body["queries"]] == [
        base,
        f"{base} when:7d",
        f"{base} sourcelang:spanish sourcecountry:MX",
        'contiene: ciberataque, hackeo, ransomware, "filtración de datos" o phishing'
        " · lugar: Iztapalapa · sin: curso, webinar o diplomado",
    ]
    assert body["region"]["breadcrumb"] == "México › Ciudad de México › Iztapalapa"


def test_vista_previa_de_un_estado_con_terminos_curados(client: TestClient, engine: Engine) -> None:
    body = client.post(
        f"{URL}/preview", params={"region_id": region_id(engine, "15")}, json=BODY
    ).json()

    assert '("Estado de México" OR Edomex) -curso' in body["queries"][0]["text"]
    # Probar un borrador no guarda nada ni deja rastro en la bitácora.
    assert client.get(URL).json()["items"] == []
    assert audit(engine) == []
