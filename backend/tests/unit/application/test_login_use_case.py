"""Entrar con usuario, contraseña y código de 6 dígitos (ADR-0043), sin base."""

from dataclasses import replace

import pytest

from app.domain.access import AuthUser, Role
from app.domain.credentials import (
    MAX_USER_FAILURES,
    hash_password,
    new_totp_secret,
    totp_code,
    totp_counter,
    verify_password,
)
from app.domain.errors import (
    AuthenticationRequiredError,
    InvalidRequestError,
    TooManyAttemptsError,
)
from tests.unit.fake_access import AccessWorld, FakeBox, access_world

pytestmark = pytest.mark.anyio

IP = "192.168.0.50"
PASSWORD = "Contraseña-segura-2026"
SECRET = new_totp_secret()


@pytest.fixture
def world() -> AccessWorld:
    w = access_world()
    # benji ya tiene contraseña propia y Authenticator dado de alta.
    creds = w.store.creds[1]
    creds.password_hash = hash_password(PASSWORD)
    creds.must_change = False
    creds.totp_secret = FakeBox().seal(SECRET)
    return w


def _code(world: AccessWorld, secret: str = SECRET, shift: int = 0) -> str:
    return totp_code(secret, totp_counter(world.clock()) + shift)


async def test_contrasena_y_codigo_abren_la_sesion(world: AccessWorld) -> None:
    step = await world.login.start("Benji ", PASSWORD, IP)

    opened = await world.login.verify_code(step.ticket, _code(world), IP)

    assert step.next == "code"
    assert opened.user.username == "benji"
    assert opened.max_seconds == 30 * 24 * 3600
    assert (await world.auth.from_session(opened.token)).username == "benji"
    assert step.ticket not in world.tickets.data
    assert world.store.events[-1][0].action == "auth.login"
    assert world.store.users[1].last_seen_at is not None


@pytest.mark.parametrize(
    ("username", "password"),
    [("benji", "otra-contraseña-1"), ("nadie", PASSWORD), ("", PASSWORD)],
)
async def test_mismo_mensaje_si_falla_el_usuario_o_la_contrasena(
    world: AccessWorld, username: str, password: str
) -> None:
    with pytest.raises(AuthenticationRequiredError) as error:
        await world.login.start(username, password, IP)

    assert error.value.message.startswith("Usuario o contraseña incorrectos")
    assert world.tickets.data == {}
    assert world.store.events[-1][0].action == "auth.login_failed"


async def test_cinco_fallos_bloquean_la_cuenta_15_minutos(world: AccessWorld) -> None:
    world.limiter.max = 100
    for _ in range(MAX_USER_FAILURES):
        with pytest.raises(AuthenticationRequiredError):
            await world.login.start("benji", "mala-contraseña-1", IP)

    # Bloqueada: ni con la contraseña buena entra (y el mensaje no lo delata).
    with pytest.raises(AuthenticationRequiredError, match="incorrectos"):
        await world.login.start("benji", PASSWORD, "10.0.0.2")
    world.clock.advance(minutes=16)
    # Pasado el bloqueo, un error más no vuelve a bloquear: se cuenta desde cero.
    with pytest.raises(AuthenticationRequiredError):
        await world.login.start("benji", "mala-contraseña-1", "10.0.0.3")
    assert (world.store.creds[1].failed, world.store.creds[1].locked_until) == (1, None)
    step = await world.login.start("benji", PASSWORD, "10.0.0.3")
    await world.login.verify_code(step.ticket, _code(world), "10.0.0.3")
    assert world.store.creds[1].failed == 0


async def test_la_ip_que_falla_mucho_queda_bloqueada(world: AccessWorld) -> None:
    for _ in range(world.limiter.max):
        with pytest.raises(AuthenticationRequiredError):
            await world.login.start("nadie", "x", IP)

    with pytest.raises(TooManyAttemptsError):
        await world.login.start("benji", PASSWORD, IP)


async def test_persona_desactivada_no_entra(world: AccessWorld) -> None:
    world.store.users[1] = replace(world.store.users[1], is_active=False)

    with pytest.raises(AuthenticationRequiredError):
        await world.login.start("benji", PASSWORD, IP)


async def test_codigo_equivocado_y_luego_el_bueno(world: AccessWorld) -> None:
    step = await world.login.start("benji", PASSWORD, IP)

    with pytest.raises(AuthenticationRequiredError, match="código no es correcto"):
        await world.login.verify_code(step.ticket, "000000", IP)
    opened = await world.login.verify_code(step.ticket, _code(world), IP)

    assert opened.user.username == "benji"


async def test_cinco_codigos_equivocados_cancelan_el_ingreso(world: AccessWorld) -> None:
    world.limiter.max = 100
    step = await world.login.start("benji", PASSWORD, IP)
    for _ in range(4):
        with pytest.raises(AuthenticationRequiredError, match="código"):
            await world.login.verify_code(step.ticket, "000000", IP)

    with pytest.raises(AuthenticationRequiredError, match="venció"):
        await world.login.verify_code(step.ticket, "000000", IP)
    with pytest.raises(AuthenticationRequiredError, match="venció"):
        await world.login.verify_code(step.ticket, _code(world), IP)


async def test_un_codigo_no_sirve_dos_veces(world: AccessWorld) -> None:
    code = _code(world)
    first = await world.login.start("benji", PASSWORD, IP)
    await world.login.verify_code(first.ticket, code, IP)

    second = await world.login.start("benji", PASSWORD, IP)
    with pytest.raises(AuthenticationRequiredError):
        await world.login.verify_code(second.ticket, code, IP)


async def test_se_acepta_el_codigo_de_hace_30_segundos(world: AccessWorld) -> None:
    step = await world.login.start("benji", PASSWORD, IP)

    opened = await world.login.verify_code(step.ticket, _code(world, shift=-1), IP)

    assert opened.user.username == "benji"


async def test_un_codigo_de_hace_dos_minutos_no_sirve(world: AccessWorld) -> None:
    step = await world.login.start("benji", PASSWORD, IP)

    with pytest.raises(AuthenticationRequiredError):
        await world.login.verify_code(step.ticket, _code(world, shift=-4), IP)


async def test_un_ticket_inventado_no_sirve(world: AccessWorld) -> None:
    with pytest.raises(AuthenticationRequiredError, match="venció"):
        await world.login.verify_code("ingreso-inventado", _code(world), IP)


async def test_primer_ingreso_completo(world: AccessWorld) -> None:
    admin_user = AuthUser(1, "benji", "Benji", Role.SUPERUSER)
    created = await world.admin.create_user(
        admin_user, IP, username="ana", display_name="Ana", email=None, role=Role.USER
    )
    ana = created.account.user_id

    step = await world.login.start("ana", created.temporary_password, IP)
    assert step.next == "change_password"
    # Sin cambiar la temporal no hay QR ni código.
    with pytest.raises(AuthenticationRequiredError):
        await world.login.start_enrollment(step.ticket)
    with pytest.raises(AuthenticationRequiredError):
        await world.login.verify_code(step.ticket, "123456", IP)
    with pytest.raises(InvalidRequestError, match="distinta"):
        await world.login.change_password(step.ticket, created.temporary_password, IP)

    step = await world.login.change_password(step.ticket, "Mi-contraseña-nueva-7", IP)
    assert step.next == "enroll"
    enrollment = await world.login.start_enrollment(step.ticket)
    assert enrollment.uri.startswith("otpauth://totp/")
    assert enrollment.secret in enrollment.uri
    assert enrollment.qr_svg.startswith("<svg>")
    # Mientras no confirme, el secreto va cifrado y no está en su cuenta.
    pending = world.tickets.data[step.ticket].pending_secret
    assert pending is not None and enrollment.secret not in pending
    assert world.store.creds[ana].totp_secret is None

    opened = await world.login.confirm_enrollment(step.ticket, _code(world, enrollment.secret), IP)

    assert opened.user.username == "ana"
    assert world.store.creds[ana].totp_secret == pending
    assert world.store.creds[ana].must_change is False
    assert verify_password("Mi-contraseña-nueva-7", world.store.creds[ana].password_hash)


async def test_la_contrasena_nueva_debe_cumplir_las_reglas(world: AccessWorld) -> None:
    world.store.creds[1].must_change = True
    step = await world.login.start("benji", PASSWORD, IP)

    for bad in ("corta1", "sinnumerosparanada", "benji-12345678"):
        with pytest.raises(InvalidRequestError):
            await world.login.change_password(step.ticket, bad, IP)


async def test_alta_del_autenticador_con_codigo_equivocado(world: AccessWorld) -> None:
    world.store.creds[1].totp_secret = None
    step = await world.login.start("benji", PASSWORD, IP)
    assert step.next == "enroll"
    await world.login.start_enrollment(step.ticket)

    with pytest.raises(AuthenticationRequiredError, match="código"):
        await world.login.confirm_enrollment(step.ticket, "000000", IP)
    assert world.store.creds[1].totp_secret is None


async def test_confirmar_sin_haber_pedido_el_qr(world: AccessWorld) -> None:
    world.store.creds[1].totp_secret = None
    step = await world.login.start("benji", PASSWORD, IP)

    with pytest.raises(AuthenticationRequiredError):
        await world.login.confirm_enrollment(step.ticket, "123456", IP)


async def test_cambiar_mi_contrasena_cierra_las_demas_sesiones(world: AccessWorld) -> None:
    step = await world.login.start("benji", PASSWORD, IP)
    other = await world.login.verify_code(step.ticket, _code(world), IP)
    user = other.user

    with pytest.raises(InvalidRequestError, match="actual no es correcta"):
        await world.login.change_own_password(user, "equivocada-1", "Nueva-contraseña-99", IP)
    fresh = await world.login.change_own_password(user, PASSWORD, "Nueva-contraseña-99", IP)

    assert other.token not in world.sessions.data
    assert fresh.token in world.sessions.data
    assert verify_password("Nueva-contraseña-99", world.store.creds[1].password_hash)
