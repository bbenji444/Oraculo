"""El candado de la API (AUTH_MODE=keys) con todo en memoria (ADR-0042 y 0043).

Revisa lo que ve un navegador o un sistema:

- sin sesión no se pasa;
- se entra con usuario, contraseña y código de 6 dígitos, y el primer
  ingreso pide cambiar la temporal y dar de alta Microsoft Authenticator;
- la cookie es ``HttpOnly`` y ``SameSite=Strict``;
- con cookie, lo que cambia algo pide ``Origin`` del mismo servidor (CSRF);
- la llave de sistema en ``Authorization: Bearer`` funciona sin cookie;
- un usuario normal no abre lo del superusuario;
- otro módulo puede preguntar de quién es un token (``/auth/introspect``).
"""

from collections.abc import Iterator

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import SESSION_COOKIE
from app.core.config import Settings
from app.domain.access import AuthUser, Role
from app.domain.credentials import hash_password, new_totp_secret, totp_code, totp_counter
from app.main import create_app
from tests.unit.fake_access import PEPPER, AccessWorld, FakeBox, access_world

ME = "/api/v1/auth/me"
LOGIN = "/api/v1/auth/login"
USERS = "/api/v1/access/users"
SAME_ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "Contraseña-segura-2026"
BENJI = AuthUser(1, "benji", "Benjamin", Role.SUPERUSER)


@pytest.fixture
def world() -> AccessWorld:
    return access_world()


def _ready(world: AccessWorld, user_id: int, secret: str) -> None:
    """Deja a la persona con contraseña propia y Authenticator dado de alta."""
    creds = world.store.creds[user_id]
    creds.password_hash = hash_password(PASSWORD)
    creds.must_change = False
    creds.totp_secret = FakeBox().seal(secret)


@pytest.fixture
def secret(world: AccessWorld) -> str:
    value = new_totp_secret()
    _ready(world, 1, value)
    return value


@pytest.fixture
def app(world: AccessWorld) -> FastAPI:
    application = create_app(Settings(auth_mode="keys", auth_key_pepper=PEPPER.decode()))
    # Sin lifespan: se ponen a mano los casos de uso en memoria.
    application.state.authenticator = world.auth
    application.state.access_admin = world.admin
    application.state.password_login = world.login
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    yield TestClient(app)


def _code(world: AccessWorld, secret: str) -> str:
    return totp_code(secret, totp_counter(world.clock()))


def _enter(client: TestClient, world: AccessWorld, username: str, secret: str) -> None:
    step = client.post(LOGIN, json={"username": username, "password": PASSWORD}).json()
    response = client.post(
        f"{LOGIN}/code", json={"ticket": step["ticket"], "code": _code(world, secret)}
    )
    assert response.status_code == 200, response.text


def _system_key(world: AccessWorld, user_id: int) -> str:
    async def issue() -> str:
        return (await world.admin.issue_key(BENJI, None, user_id, "sistema", None)).key.full

    # TestClient es síncrono: la llave se crea con su propio ciclo de asyncio.
    return anyio.run(issue)


def test_sin_sesion_no_se_pasa(client: TestClient) -> None:
    for path in (ME, "/api/v1/concepts", "/api/v1/searches", USERS, "/api/v1/docs"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "auth_required"
        assert "usuario y contraseña" in response.json()["error"]["message"]


def test_salir_es_publico_y_no_falla_sin_sesion(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_entrar_con_contrasena_y_codigo(
    client: TestClient, world: AccessWorld, secret: str
) -> None:
    step = client.post(LOGIN, json={"username": "benji", "password": PASSWORD})

    assert step.status_code == 200
    assert step.json()["next"] == "code"
    assert step.headers["cache-control"] == "no-store"
    assert SESSION_COOKIE not in step.cookies
    done = client.post(
        f"{LOGIN}/code", json={"ticket": step.json()["ticket"], "code": _code(world, secret)}
    )

    assert done.status_code == 200
    assert done.json()["role"] == "superuser"
    cookie = done.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api" in cookie
    assert f"max-age={30 * 24 * 3600}" in cookie
    assert client.get(ME).json()["username"] == "benji"


def test_contrasena_mala_o_codigo_malo(client: TestClient, world: AccessWorld, secret: str) -> None:
    bad = client.post(LOGIN, json={"username": "benji", "password": "otra-cosa-123"})
    step = client.post(LOGIN, json={"username": "benji", "password": PASSWORD}).json()
    wrong = client.post(f"{LOGIN}/code", json={"ticket": step["ticket"], "code": "000000"})

    assert bad.status_code == 401
    assert "incorrectos" in bad.json()["error"]["message"]
    assert wrong.status_code == 401
    assert "código" in wrong.json()["error"]["message"]
    assert client.get(ME).status_code == 401


def test_primer_ingreso_por_http(client: TestClient, world: AccessWorld, secret: str) -> None:
    _enter(client, world, "benji", secret)
    created = client.post(
        USERS, json={"username": "ana", "display_name": "Ana"}, headers=SAME_ORIGIN
    ).json()
    ana = TestClient(client.app)

    step = ana.post(
        LOGIN, json={"username": "ana", "password": created["temporary_password"]}
    ).json()
    assert step["next"] == "change_password"
    weak = ana.post(f"{LOGIN}/password", json={"ticket": step["ticket"], "new_password": "corta"})
    assert weak.status_code == 422
    step = ana.post(
        f"{LOGIN}/password",
        json={"ticket": step["ticket"], "new_password": "Mi-clave-fuerte-2026"},
    ).json()
    assert step["next"] == "enroll"
    enrollment = ana.post(f"{LOGIN}/enroll", json={"ticket": step["ticket"]}).json()
    assert enrollment["uri"].startswith("otpauth://totp/")
    done = ana.post(
        f"{LOGIN}/enroll/confirm",
        json={"ticket": step["ticket"], "code": _code(world, enrollment["secret"])},
    )

    assert done.status_code == 200
    assert ana.get(ME).json()["username"] == "ana"


def test_con_cookie_los_cambios_piden_el_mismo_origen(
    client: TestClient, world: AccessWorld, secret: str
) -> None:
    _enter(client, world, "benji", secret)
    body = {"username": "ana", "display_name": "Ana"}

    no_origin = client.post(USERS, json=body)
    evil = client.post(USERS, json=body, headers={"Origin": "http://malo.example"})
    ok = client.post(USERS, json=body, headers=SAME_ORIGIN)

    assert (no_origin.status_code, no_origin.json()["error"]["code"]) == (403, "forbidden")
    assert evil.status_code == 403
    assert ok.status_code == 201
    assert ok.json()["user"]["must_change_password"] is True
    assert len(ok.json()["temporary_password"]) == 16
    assert ok.headers["cache-control"] == "no-store"


def test_la_llave_de_sistema_sirve_sin_cookie_ni_origen(
    client: TestClient, world: AccessWorld
) -> None:
    headers = {"Authorization": f"Bearer {_system_key(world, 1)}"}

    me = client.get(ME, headers=headers)
    created = client.post(USERS, json={"username": "pepe", "display_name": "Pepe"}, headers=headers)

    assert me.json()["username"] == "benji"
    assert created.status_code == 201
    assert SESSION_COOKIE not in client.cookies


def test_bearer_falso(client: TestClient) -> None:
    assert client.get(ME, headers={"Authorization": "Bearer orc_live_nada"}).status_code == 401


def test_un_usuario_normal_no_abre_lo_del_superusuario(
    client: TestClient, world: AccessWorld
) -> None:
    ana = world.store.add_user("ana")
    ana_secret = new_totp_secret()
    _ready(world, ana, ana_secret)
    _enter(client, world, "ana", ana_secret)

    me = client.get(ME).json()

    assert me["role"] == "user"
    assert me["sections"] == ["explorar", "casos", "conceptos", "historial"]
    for path in (USERS, "/api/v1/schedule", "/api/v1/deliveries/overview"):
        assert client.get(path).status_code == 403, path
    concept = client.post(
        "/api/v1/concepts", json={"name": "X", "keywords": ["x"]}, headers=SAME_ORIGIN
    )
    assert concept.status_code == 403
    assert "superusuario" in concept.json()["error"]["message"]


def test_restablecer_contrasena_saca_al_instante(
    client: TestClient, world: AccessWorld, secret: str
) -> None:
    ana = world.store.add_user("ana")
    ana_secret = new_totp_secret()
    _ready(world, ana, ana_secret)
    ana_client = TestClient(client.app)
    _enter(ana_client, world, "ana", ana_secret)
    _enter(client, world, "benji", secret)

    reset = client.post(f"{USERS}/{ana}/reset-password", headers=SAME_ORIGIN)
    after = ana_client.get(ME)

    assert reset.status_code == 200
    assert len(reset.json()["temporary_password"]) == 16
    assert after.status_code == 401
    # Y el navegador borra la cookie vencida.
    assert f"{SESSION_COOKIE}=" in after.headers.get("set-cookie", "")


def test_reiniciar_autenticador(client: TestClient, world: AccessWorld, secret: str) -> None:
    ana = world.store.add_user("ana")
    _ready(world, ana, new_totp_secret())
    _enter(client, world, "benji", secret)

    response = client.post(f"{USERS}/{ana}/reset-totp", headers=SAME_ORIGIN)
    step = TestClient(client.app).post(LOGIN, json={"username": "ana", "password": PASSWORD})

    assert response.status_code == 204
    assert step.json()["next"] == "enroll"


def test_cambiar_mi_contrasena(client: TestClient, world: AccessWorld, secret: str) -> None:
    _enter(client, world, "benji", secret)

    wrong = client.post(
        "/api/v1/auth/password",
        json={"current_password": "no-es-esta-1", "new_password": "Otra-contraseña-77"},
        headers=SAME_ORIGIN,
    )
    ok = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "Otra-contraseña-77"},
        headers=SAME_ORIGIN,
    )

    # Equivocarse de contraseña actual no saca a nadie (422, no 401).
    assert wrong.status_code == 422
    assert ok.status_code == 200
    assert client.get(ME).json()["username"] == "benji"


def test_otro_modulo_pregunta_de_quien_es_un_token(
    client: TestClient, world: AccessWorld, secret: str
) -> None:
    _enter(client, world, "benji", secret)
    token = client.cookies[SESSION_COOKIE]
    system = {"Authorization": f"Bearer {_system_key(world, 1)}"}
    stranger = TestClient(client.app)

    found = stranger.post("/api/v1/auth/introspect", json={"token": token}, headers=system)
    missing = stranger.post("/api/v1/auth/introspect", json={"token": "x" * 40}, headers=system)
    anonymous = stranger.post("/api/v1/auth/introspect", json={"token": token})

    assert found.json() == {
        "active": True,
        "username": "benji",
        "display_name": "Benji",
        "role": "superuser",
    }
    assert missing.json()["active"] is False
    assert anonymous.status_code == 401


def test_demasiados_intentos_responden_429(client: TestClient, secret: str) -> None:
    for _ in range(3):
        client.post(LOGIN, json={"username": "benji", "password": "mala-contraseña-1"})

    response = client.post(LOGIN, json={"username": "benji", "password": PASSWORD})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_attempts"


def test_en_modo_dev_se_entra_sin_contrasena_como_superusuario() -> None:
    client = TestClient(create_app(Settings(auth_mode="dev", dev_user="benji")))

    me = client.get(ME).json()

    assert (me["username"], me["role"], me["auth_mode"]) == ("benji", "superuser", "dev")
    assert client.post(LOGIN, json={"username": "x", "password": "y"}).status_code == 409


def test_en_modo_keys_sin_pimienta_no_arranca() -> None:
    with pytest.raises(ValueError, match="AUTH_KEY_PEPPER"):
        Settings(auth_mode="keys", auth_key_pepper=None)
    with pytest.raises(ValueError, match="AUTH_KEY_PEPPER"):
        Settings(auth_mode="keys", auth_key_pepper="corta")


def test_borrar_a_una_persona_la_saca_y_ya_no_entra(
    client: TestClient, world: AccessWorld, secret: str
) -> None:
    ana = world.store.add_user("ana")
    ana_secret = new_totp_secret()
    _ready(world, ana, ana_secret)
    ana_client = TestClient(client.app)
    _enter(ana_client, world, "ana", ana_secret)
    _enter(client, world, "benji", secret)

    no_origin = client.delete(f"{USERS}/{ana}")
    deleted = client.delete(f"{USERS}/{ana}", headers=SAME_ORIGIN)
    again = client.delete(f"{USERS}/{ana}", headers=SAME_ORIGIN)
    myself = client.delete(f"{USERS}/1", headers=SAME_ORIGIN)

    assert no_origin.status_code == 403
    assert deleted.status_code == 204
    assert again.status_code == 404
    assert myself.status_code == 409
    assert ana_client.get(ME).status_code == 401
    assert "ana" not in [u["username"] for u in client.get(USERS).json()["items"]]
    login = TestClient(client.app).post(LOGIN, json={"username": "ana", "password": PASSWORD})
    assert login.status_code == 401
