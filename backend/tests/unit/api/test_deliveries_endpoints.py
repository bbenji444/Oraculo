"""«Envíos» por persona en la API (ADR-0045), con piezas en memoria.

Prueba lo que decide la API: a nombre de quién queda cada correo, el tope de
dos para un usuario normal, las horas («HH:MM») dentro del horario, que el
usuario no elija la cuenta que envía y que cuentas y reglas sean del
superusuario. Que cada quien vea solo lo suyo lo hace la base (seguridad por
filas) y se prueba en ``tests/integration/test_deliveries_repository.py``.
"""

from collections.abc import Iterator

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.deliveries import OverviewOut, SourceOut
from app.application.ports.deliveries import RuleDraft
from app.application.use_cases.deliveries import SendDeliveries
from app.core.config import Settings
from app.domain.concept import ConceptDraft
from app.domain.credentials import hash_password, new_totp_secret, totp_code, totp_counter
from app.domain.deliveries import (
    SOURCE_FGR_RUN,
    SOURCES,
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
)
from app.domain.schedule import RunSchedule
from app.main import create_app
from tests.unit.fake_access import PEPPER, AccessWorld, FakeBox, access_world
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_deliveries import (
    NOW,
    FakeConnector,
    FakeDeliveryStore,
    FakeReports,
    FakeSender,
)
from tests.unit.fake_delivery_schedules import FakeDeliveryScheduleStore
from tests.unit.fake_regions import CDMX, FakeRegionRepository

LOGIN = "/api/v1/auth/login"
RECIPIENTS = "/api/v1/deliveries/recipients"
SAME_ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "Contraseña-segura-2026"
# El horario de siempre de la FGR: 07:00, 15:00 y 23:00.
FGR_HOURS = (7, 15, 23)


class _NoStoredSchedule:
    """Nadie ha editado el horario: vale el de ``AUTOMATIC_RUN_HOURS``."""

    async def get(self) -> None:
        return None

    async def average_run_cost(self, since: object) -> None:
        return None


class _World:
    def __init__(self) -> None:
        self.access: AccessWorld = access_world()
        self.store = FakeDeliveryStore()
        self.sender = FakeSender()
        self.schedules = FakeDeliveryScheduleStore()
        self.concepts = FakeConceptRepository()
        self.concepts.add(
            ConceptDraft.validated(
                name="Extorsión",
                description="",
                keywords=("extorsión",),
                exclude_terms=(),
                color="#00D2FF",
                is_active=True,
            )
        )


@pytest.fixture
def world() -> _World:
    return _World()


@pytest.fixture
def client(world: _World) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(auth_mode="keys", auth_key_pepper=PEPPER.decode()))
    # Sin lifespan: se ponen a mano los casos de uso en memoria.
    app.state.authenticator = world.access.auth
    app.state.access_admin = world.access.admin
    app.state.password_login = world.access.login
    reports = FakeReports()
    app.state.delivery_store = world.store
    app.state.delivery_reports = reports
    app.state.delivery_connector = FakeConnector()
    app.state.delivery_sender = SendDeliveries(
        world.store, reports, {DeliveryChannel.EMAIL: world.sender}, now=lambda: NOW
    )
    app.state.delivery_overview = OverviewOut(
        enabled=True,
        email_configured=True,
        whatsapp_available=False,
        sources=[SourceOut(id=k, label=v) for k, v in SOURCES.items()],
    )
    app.state.schedule_store = _NoStoredSchedule()
    app.state.schedule_default = RunSchedule.from_hours(FGR_HOURS)
    app.state.automatic_runs_enabled = True
    app.state.delivery_schedule_store = world.schedules
    app.state.concept_repository = world.concepts
    app.state.region_repository = FakeRegionRepository()

    async def sender_account() -> None:
        account = await world.store.save_account(
            AccountProvider.OUTLOOK, "Ovitech", "ca_1", AccountStatus.ACTIVE
        )
        await world.store.update_account(account.id, AccountStatus.ACTIVE, "ovitech_22@hotmail.com")
        await world.store.save_rule(
            RuleDraft(SOURCE_FGR_RUN, DeliveryChannel.EMAIL, account.id, is_active=True)
        )

    anyio.run(sender_account)
    yield TestClient(app)


def _enter(client: TestClient, world: _World, username: str) -> None:
    """Entra como la persona (la crea si no es Benji, el superusuario 1)."""
    user_id = 1 if username == "benji" else world.access.store.add_user(username)
    secret = new_totp_secret()
    creds = world.access.store.creds[user_id]
    creds.password_hash = hash_password(PASSWORD)
    creds.must_change = False
    creds.totp_secret = FakeBox().seal(secret)
    step = client.post(LOGIN, json={"username": username, "password": PASSWORD}).json()
    code = totp_code(secret, totp_counter(world.access.clock()))
    response = client.post(f"{LOGIN}/code", json={"ticket": step["ticket"], "code": code})
    assert response.status_code == 200, response.text


def _add(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        RECIPIENTS, json={"name": "Mi correo", "email": email}, headers=SAME_ORIGIN
    )
    return {"status": response.status_code, **response.json()}


def test_un_usuario_agrega_hasta_dos_correos_a_su_nombre(client: TestClient, world: _World) -> None:
    _enter(client, world, "ana")

    first = _add(client, "ana@x.mx")
    second = _add(client, "ana@fgr.mx")
    third = _add(client, "ana3@x.mx")

    assert (first["status"], first["owner"]) == (201, "ana")
    assert second["status"] == 201
    assert third["status"] == 422
    overview = client.get("/api/v1/deliveries/overview").json()
    # Benji, 11/11/2026: al usuario no se le dice desde qué correo se manda.
    assert (overview["max_recipients"], overview["sender_address"]) == (2, None)


def test_el_usuario_no_elige_la_cuenta_que_envia(client: TestClient, world: _World) -> None:
    _enter(client, world, "ana")
    recipient = _add(client, "ana@x.mx")

    response = client.post(
        "/api/v1/deliveries/test",
        json={"recipient_id": recipient["id"], "account_id": 99},
        headers=SAME_ORIGIN,
    )

    # La cuenta 99 no existe: si la hubiera tomado, sería 404.
    assert response.status_code == 200, response.text
    assert (response.json()["account_id"], response.json()["owner"]) == (1, "ana")
    assert world.sender.sent[0].destination == "ana@x.mx"


def test_cuentas_reglas_y_horario_son_del_superusuario(client: TestClient, world: _World) -> None:
    _enter(client, world, "ana")
    for path in ("/api/v1/deliveries/accounts", "/api/v1/deliveries/rules"):
        assert client.get(path).status_code == 403, path
    rule = {"source": SOURCE_FGR_RUN, "account_id": 1}
    assert client.put("/api/v1/deliveries/rules", json=rule, headers=SAME_ORIGIN).status_code == 403
    assert client.get("/api/v1/schedule").json()["times"] == ["07:00", "15:00", "23:00"]

    _enter(client, world, "benji")
    assert client.get("/api/v1/deliveries/accounts").status_code == 200
    for n in range(3):
        assert _add(client, f"lista{n}@x.mx")["status"] == 201
    overview = client.get("/api/v1/deliveries/overview").json()
    assert (overview["max_recipients"], overview["sender_address"]) == (
        None,
        "ovitech_22@hotmail.com",
    )


SCHEDULES = "/api/v1/deliveries/schedules"


def _schedule(client: TestClient, times: list[str], recipients: list[object]) -> dict[str, object]:
    body = {
        "name": "Extorsión CDMX tarde",
        "concept_ids": [1],
        "region_id": CDMX.id,
        "times": times,
        "days": [1, 2, 3, 4, 5],
        "recipient_ids": recipients,
    }
    response = client.post(SCHEDULES, json=body, headers=SAME_ORIGIN)
    return {"status": response.status_code, **response.json()}


def test_un_usuario_programa_su_envio_a_la_hora_que_quiera(
    client: TestClient, world: _World
) -> None:
    _enter(client, world, "ana")
    mail = _add(client, "ana@x.mx")

    saved = _schedule(client, ["16:00", "20:00"], [mail["id"]])
    too_many = _schedule(client, ["09:30", "12:00"], [mail["id"]])
    listing = client.get(SCHEDULES).json()

    assert saved["status"] == 201, saved
    assert (saved["owner"], saved["times"], saved["concept_names"]) == (
        "ana",
        ["16:00", "20:00"],
        ["Extorsión"],
    )
    assert (saved["region_name"], saved["runs_per_day"]) == (CDMX.name, 2)
    # 2 + 2 pasa de su tope de 3 corridas al día.
    assert too_many["status"] == 422
    assert (listing["daily_runs"], listing["daily_limit"]) == (2, 3)


def test_cambiar_y_borrar_un_envio_programado(client: TestClient, world: _World) -> None:
    _enter(client, world, "ana")
    saved = _schedule(client, ["16:00"], [])

    changed = client.put(
        f"{SCHEDULES}/{saved['id']}",
        json={
            "name": "Solo en la noche",
            "concept_ids": [1],
            "region_id": CDMX.id,
            "times": ["21:15"],
            "is_active": False,
        },
        headers=SAME_ORIGIN,
    )
    deleted = client.delete(f"{SCHEDULES}/{saved['id']}", headers=SAME_ORIGIN)

    assert changed.status_code == 200, changed.text
    assert (changed.json()["times"], changed.json()["upcoming"]) == (["21:15"], [])
    assert deleted.status_code == 204
    assert client.get(SCHEDULES).json()["items"] == []
