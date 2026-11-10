"""El candado de la API con llaves (AUTH_MODE=keys), con todo en memoria (ADR-0042).

Revisa lo que ve un navegador o una integración: sin llave no se pasa; la
cookie es ``HttpOnly`` y ``SameSite=Strict``; las peticiones que cambian algo
con cookie necesitan ``Origin`` del mismo servidor (CSRF); la llave en
``Authorization: Bearer`` funciona sin cookie; y un usuario normal no abre lo
del superusuario.
"""

from collections.abc import Iterator

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import SESSION_COOKIE
from app.core.config import Settings
from app.domain.access import AuthUser, Role
from app.main import create_app
from tests.unit.fake_access import PEPPER, AccessWorld, access_world

ME = "/api/v1/auth/me"
LOGIN = "/api/v1/auth/login"
USERS = "/api/v1/access/users"
SAME_ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def world() -> AccessWorld:
    return access_world()


@pytest.fixture
def app(world: AccessWorld) -> FastAPI:
    application = create_app(Settings(auth_mode="keys", auth_key_pepper=PEPPER.decode()))
    # Sin lifespan: se ponen a mano el autenticador y la administración.
    application.state.authenticator = world.auth
    application.state.access_admin = world.admin
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    yield TestClient(app)


async def _issue(world: AccessWorld, user_id: int) -> str:
    admin = AuthUser(1, "benji", "Benjamin", Role.SUPERUSER)
    return (await world.admin.issue_key(admin, None, user_id, "prueba", None)).key.full


def _key(world: AccessWorld, user_id: int) -> str:
    # TestClient es síncrono: la llave se crea con su propio ciclo de asyncio.
    return anyio.run(_issue, world, user_id)


@pytest.fixture
def benji_key(world: AccessWorld) -> str:
    return _key(world, 1)


@pytest.fixture
def ana_key(world: AccessWorld) -> str:
    return _key(world, world.store.add_user("ana"))


def test_sin_llave_no_se_pasa(client: TestClient) -> None:
    for path in (ME, "/api/v1/concepts", "/api/v1/searches", USERS, "/api/v1/docs"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "auth_required"


def test_salir_es_publico_y_no_falla_sin_sesion(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_llave_falsa(client: TestClient) -> None:
    response = client.post(LOGIN, json={"key": "orc_live_ABCDEFGH_" + "x" * 40})

    assert response.status_code == 401
    assert "no es válida" in response.json()["error"]["message"]
    assert SESSION_COOKIE not in response.cookies


def test_entrar_da_una_cookie_protegida_y_abre_la_sesion(
    client: TestClient, benji_key: str
) -> None:
    response = client.post(LOGIN, json={"key": benji_key})

    assert response.status_code == 200
    assert response.json()["role"] == "superuser"
    assert "estado" in response.json()["sections"]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api" in cookie
    assert benji_key.lower() not in cookie
    assert response.headers["cache-control"] == "no-store"
    assert client.get(ME).json()["username"] == "benji"


def test_salir_cierra_la_sesion(client: TestClient, benji_key: str) -> None:
    client.post(LOGIN, json={"key": benji_key})

    assert client.post("/api/v1/auth/logout").status_code == 204

    assert client.get(ME).status_code == 401


def test_con_cookie_los_cambios_piden_el_mismo_origen(client: TestClient, benji_key: str) -> None:
    client.post(LOGIN, json={"key": benji_key})
    body = {"username": "ana", "display_name": "Ana"}

    no_origin = client.post(USERS, json=body)
    evil = client.post(USERS, json=body, headers={"Origin": "http://malo.example"})
    ok = client.post(USERS, json=body, headers=SAME_ORIGIN)

    assert (no_origin.status_code, no_origin.json()["error"]["code"]) == (403, "forbidden")
    assert evil.status_code == 403
    assert ok.status_code == 201
    assert ok.json()["username"] == "ana"


def test_la_llave_bearer_sirve_sin_cookie_ni_origen(client: TestClient, benji_key: str) -> None:
    headers = {"Authorization": f"Bearer {benji_key}"}

    me = client.get(ME, headers=headers)
    created = client.post(USERS, json={"username": "pepe", "display_name": "Pepe"}, headers=headers)

    assert me.json()["username"] == "benji"
    assert created.status_code == 201
    assert SESSION_COOKIE not in client.cookies


def test_bearer_falso(client: TestClient) -> None:
    response = client.get(ME, headers={"Authorization": "Bearer orc_live_nada"})

    assert response.status_code == 401


def test_un_usuario_normal_no_abre_lo_del_superusuario(client: TestClient, ana_key: str) -> None:
    me = client.post(LOGIN, json={"key": ana_key}).json()

    assert me["role"] == "user"
    assert me["sections"] == ["explorar", "casos", "conceptos", "historial"]
    for path in (USERS, "/api/v1/schedule", "/api/v1/deliveries/overview"):
        response = client.get(path)
        assert response.status_code == 403, path
    concept = client.post(
        "/api/v1/concepts", json={"name": "X", "keywords": ["x"]}, headers=SAME_ORIGIN
    )
    assert concept.status_code == 403
    assert "superusuario" in concept.json()["error"]["message"]


def test_la_revocacion_saca_al_instante(
    client: TestClient, world: AccessWorld, ana_key: str
) -> None:
    client.post(LOGIN, json={"key": ana_key})
    assert client.get(ME).status_code == 200
    [key] = [k for k in world.store.keys.values() if k.info.user_id == 2]
    other = TestClient(client.app)
    other.post(LOGIN, json={"key": _key(world, 1)})

    other.delete(f"/api/v1/access/keys/{key.info.key_id}", headers=SAME_ORIGIN)

    response = client.get(ME)
    assert response.status_code == 401
    # Y el navegador borra la cookie vencida.
    assert f"{SESSION_COOKIE}=" in response.headers.get("set-cookie", "")


def test_crear_llave_desde_accesos_la_muestra_una_sola_vez(
    client: TestClient, benji_key: str
) -> None:
    client.post(LOGIN, json={"key": benji_key})
    user = client.post(USERS, json={"username": "ana", "display_name": "Ana"}, headers=SAME_ORIGIN)

    issued = client.post(
        f"{USERS}/{user.json()['id']}/keys",
        json={"label": "Laptop", "days": 30},
        headers=SAME_ORIGIN,
    )
    listed = client.get(f"{USERS}/{user.json()['id']}/keys")

    assert issued.status_code == 201
    full = issued.json()["key"]
    assert full.startswith("orc_live_")
    assert issued.headers["cache-control"] == "no-store"
    assert full not in listed.text
    assert listed.json()["items"][0]["masked"] == full[:17] + "…"
    # La llave nueva sirve para entrar.
    assert TestClient(client.app).post(LOGIN, json={"key": full}).json()["username"] == "ana"


def test_demasiados_intentos_responden_429(client: TestClient, benji_key: str) -> None:
    for _ in range(3):
        client.post(LOGIN, json={"key": "mala"})

    response = client.post(LOGIN, json={"key": benji_key})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_attempts"


def test_en_modo_dev_se_entra_sin_llave_como_superusuario() -> None:
    client = TestClient(create_app(Settings(auth_mode="dev", dev_user="benji")))

    me = client.get(ME).json()

    assert (me["username"], me["role"], me["auth_mode"]) == ("benji", "superuser", "dev")
    assert client.post(LOGIN, json={"key": "x"}).status_code == 409


def test_en_modo_keys_sin_pimienta_no_arranca() -> None:
    with pytest.raises(ValueError, match="AUTH_KEY_PEPPER"):
        Settings(auth_mode="keys", auth_key_pepper=None)
    with pytest.raises(ValueError, match="AUTH_KEY_PEPPER"):
        Settings(auth_mode="keys", auth_key_pepper="corta")
