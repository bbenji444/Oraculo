"""Entrar con llave, sesiones y administración de accesos (ADR-0042), sin base."""

from dataclasses import replace

import pytest

from app.application.ports.access import UserChanges
from app.domain.access import MAX_ACTIVE_KEYS_PER_USER, AuthUser, Role
from app.domain.errors import (
    AccessKeyNotFoundError,
    AccessRuleError,
    AuthenticationRequiredError,
    ForbiddenError,
    InvalidRequestError,
    TooManyAttemptsError,
    UsernameTakenError,
    UserNotFoundError,
)
from tests.unit.fake_access import AccessWorld, access_world

pytestmark = pytest.mark.anyio

IP = "192.168.0.50"


@pytest.fixture
def world() -> AccessWorld:
    return access_world()


async def _admin(world: AccessWorld) -> AuthUser:
    account = await world.store.get_user(1)
    assert account is not None
    return AuthUser(account.user_id, account.username, account.display_name, account.role)


async def _key_for(world: AccessWorld, user_id: int, days: int | None = None) -> str:
    issued = await world.admin.issue_key(await _admin(world), IP, user_id, "prueba", days)
    return issued.key.full


async def test_entrar_con_una_llave_valida_abre_sesion(world: AccessWorld) -> None:
    key = await _key_for(world, 1)

    opened = await world.auth.login(key, IP)

    assert opened.user.username == "benji"
    assert opened.max_seconds == 8 * 3600
    assert (await world.auth.from_session(opened.token)).is_superuser
    assert world.store.used == [(1, IP)]
    assert world.store.events[-1][0].action == "auth.login"


async def test_la_base_nunca_guarda_la_llave_completa(world: AccessWorld) -> None:
    key = await _key_for(world, 1)

    [stored] = world.store.keys.values()

    assert key not in stored.key_hash
    assert key not in repr(stored.info)
    assert all(key not in repr(e) for e in world.store.events)


@pytest.mark.parametrize("bad", ["", "hola", "orc_live_ABCDEFGH_" + "x" * 40])
async def test_una_llave_falsa_no_entra_y_queda_en_la_bitacora(
    world: AccessWorld, bad: str
) -> None:
    with pytest.raises(AuthenticationRequiredError, match="no es válida"):
        await world.auth.login(bad, IP)

    assert world.store.events[-1][0].action == "auth.login_failed"
    assert world.limiter.failures[IP] == 1


async def test_la_parte_publica_correcta_con_secreto_falso_no_entra(world: AccessWorld) -> None:
    key = await _key_for(world, 1)
    forged = key[:-1] + ("A" if key[-1] != "A" else "B")

    with pytest.raises(AuthenticationRequiredError):
        await world.auth.login(forged, IP)
    # Quien falla no se sabe: la bitácora no le atribuye el intento a benji.
    assert world.store.events[-1][0].actor.user_id == "anonimo"


async def test_llave_revocada_vencida_o_de_persona_desactivada(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    revoked = await _key_for(world, ana)
    await world.admin.revoke_key(await _admin(world), IP, 1)
    expiring = await _key_for(world, ana, days=1)
    world.clock.advance(days=2)

    with pytest.raises(AuthenticationRequiredError):
        await world.auth.login(revoked, IP)
    with pytest.raises(AuthenticationRequiredError):
        await world.auth.login(expiring, IP)

    pepe = world.store.add_user("pepe")
    valid = await _key_for(world, pepe)
    await world.admin.update_user(await _admin(world), IP, pepe, UserChanges(is_active=False))
    with pytest.raises(AuthenticationRequiredError):
        await world.auth.login(valid, IP)


async def test_demasiados_intentos_bloquean_la_ip_aunque_luego_traiga_la_buena(
    world: AccessWorld,
) -> None:
    key = await _key_for(world, 1)
    for _ in range(world.limiter.max):
        with pytest.raises(AuthenticationRequiredError):
            await world.auth.login("mala", IP)

    with pytest.raises(TooManyAttemptsError):
        await world.auth.login(key, IP)
    # Otra IP no está bloqueada.
    assert (await world.auth.login(key, "10.0.0.9")).user.username == "benji"


async def test_entrar_bien_borra_la_cuenta_de_fallos(world: AccessWorld) -> None:
    key = await _key_for(world, 1)
    with pytest.raises(AuthenticationRequiredError):
        await world.auth.login("mala", IP)

    await world.auth.login(key, IP)

    assert IP not in world.limiter.failures


async def test_la_sesion_dura_a_lo_mas_8_horas(world: AccessWorld) -> None:
    opened = await world.auth.login(await _key_for(world, 1), IP)
    world.clock.advance(hours=8, seconds=1)

    with pytest.raises(AuthenticationRequiredError, match="sesión terminó"):
        await world.auth.from_session(opened.token)
    assert opened.token not in world.sessions.data


async def test_la_sesion_revisa_la_llave_cada_5_minutos(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    opened = await world.auth.login(await _key_for(world, ana), IP)
    # Se revoca «por fuera» (sin cerrar sesiones), como si fallara Redis.
    world.store.keys[1].info = replace(world.store.keys[1].info, revoked_at=world.clock())

    world.clock.advance(minutes=4)
    assert (await world.auth.from_session(opened.token)).username == "ana"
    world.clock.advance(minutes=2)
    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_session(opened.token)


async def test_la_revision_refresca_el_rol(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    opened = await world.auth.login(await _key_for(world, ana), IP)
    world.store.users[ana] = replace(world.store.users[ana], display_name="Ana López")
    world.clock.advance(minutes=6)

    assert (await world.auth.from_session(opened.token)).display_name == "Ana López"


async def test_salir_cierra_la_sesion(world: AccessWorld) -> None:
    opened = await world.auth.login(await _key_for(world, 1), IP)

    await world.auth.logout(opened.token)

    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_session(opened.token)


async def test_la_llave_en_bearer_reconoce_a_la_persona(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    key = await _key_for(world, ana)

    user = await world.auth.from_bearer(key, IP)

    assert (user.username, user.role) == ("ana", Role.USER)
    assert world.sessions.data == {}


async def test_un_usuario_normal_no_administra(world: AccessWorld) -> None:
    ana = AuthUser(world.store.add_user("ana"), "ana", "Ana", Role.USER)

    with pytest.raises(ForbiddenError):
        await world.admin.list_users(ana)
    with pytest.raises(ForbiddenError):
        await world.admin.issue_key(ana, IP, ana.user_id, "x", None)
    with pytest.raises(ForbiddenError):
        await world.admin.create_user(
            ana, IP, username="pepe", display_name="Pepe", email=None, role=Role.SUPERUSER
        )


async def test_alta_de_persona_y_usuario_repetido(world: AccessWorld) -> None:
    admin = await _admin(world)

    ana = await world.admin.create_user(
        admin,
        IP,
        username=" Ana.Lopez ",
        display_name="Ana  López",
        email="ANA@x.mx",
        role=Role.USER,
    )

    assert (ana.username, ana.display_name, ana.email) == ("ana.lopez", "Ana López", "ana@x.mx")
    assert world.store.events[-1][0].action == "user.created"
    with pytest.raises(UsernameTakenError):
        await world.admin.create_user(
            admin, IP, username="ana.lopez", display_name="Otra", email=None, role=Role.USER
        )


async def test_nadie_se_quita_su_rol_ni_se_desactiva(world: AccessWorld) -> None:
    admin = await _admin(world)

    with pytest.raises(AccessRuleError, match="propio"):
        await world.admin.update_user(admin, IP, 1, UserChanges(role=Role.USER))
    with pytest.raises(AccessRuleError, match="propio"):
        await world.admin.update_user(admin, IP, 1, UserChanges(is_active=False))


async def test_siempre_queda_un_superusuario_activo(world: AccessWorld) -> None:
    otro = world.store.add_user("otro", Role.SUPERUSER)
    otro_admin = AuthUser(otro, "otro", "Otro", Role.SUPERUSER)
    await world.admin.update_user(otro_admin, IP, 1, UserChanges(is_active=False))

    with pytest.raises(AccessRuleError):
        await world.admin.update_user(otro_admin, IP, otro, UserChanges(role=Role.USER))


async def test_desactivar_o_cambiar_rol_cierra_sus_sesiones(world: AccessWorld) -> None:
    admin = await _admin(world)
    ana = world.store.add_user("ana")
    opened = await world.auth.login(await _key_for(world, ana), IP)

    await world.admin.update_user(admin, IP, ana, UserChanges(role=Role.SUPERUSER))

    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_session(opened.token)


async def test_cambiar_solo_el_nombre_no_cierra_sesiones(world: AccessWorld) -> None:
    admin = await _admin(world)
    ana = world.store.add_user("ana")
    opened = await world.auth.login(await _key_for(world, ana), IP)

    updated = await world.admin.update_user(admin, IP, ana, UserChanges(display_name="Ana L."))

    assert updated.display_name == "Ana L."
    assert opened.token in world.sessions.data


async def test_persona_inexistente(world: AccessWorld) -> None:
    admin = await _admin(world)

    with pytest.raises(UserNotFoundError):
        await world.admin.update_user(admin, IP, 99, UserChanges(display_name="X"))
    with pytest.raises(UserNotFoundError):
        await world.admin.issue_key(admin, IP, 99, "x", None)
    with pytest.raises(UserNotFoundError):
        await world.admin.user_keys(admin, 99)


async def test_tope_de_llaves_vigentes_y_vigencia(world: AccessWorld) -> None:
    admin = await _admin(world)
    ana = world.store.add_user("ana")
    for _ in range(MAX_ACTIVE_KEYS_PER_USER):
        await world.admin.issue_key(admin, IP, ana, "x", 30)

    with pytest.raises(AccessRuleError, match="hasta"):
        await world.admin.issue_key(admin, IP, ana, "x", 30)
    with pytest.raises(InvalidRequestError):
        await world.admin.issue_key(admin, IP, 1, "x", 0)
    with pytest.raises(InvalidRequestError):
        await world.admin.issue_key(admin, IP, 1, "x" * 81, 30)


async def test_no_se_da_llave_a_una_persona_desactivada(world: AccessWorld) -> None:
    ana = world.store.add_user("ana", active=False)

    with pytest.raises(AccessRuleError, match="Activa"):
        await world.admin.issue_key(await _admin(world), IP, ana, "x", None)


async def test_revocar_cierra_solo_las_sesiones_de_esa_llave(world: AccessWorld) -> None:
    admin = await _admin(world)
    ana = world.store.add_user("ana")
    laptop = await world.auth.login(await _key_for(world, ana), IP)
    casa = await world.auth.login(await _key_for(world, ana), IP)

    revoked = await world.admin.revoke_key(admin, IP, 1)

    assert revoked.revoked_at is not None
    assert laptop.token not in world.sessions.data
    assert casa.token in world.sessions.data


async def test_no_puedes_revocar_tu_unica_llave(world: AccessWorld) -> None:
    await _key_for(world, 1)

    with pytest.raises(AccessRuleError, match="única"):
        await world.admin.revoke_key(await _admin(world), IP, 1)
    await _key_for(world, 1)
    assert (await world.admin.revoke_key(await _admin(world), IP, 1)).revoked_at is not None


async def test_revocar_una_llave_que_no_existe(world: AccessWorld) -> None:
    with pytest.raises(AccessKeyNotFoundError):
        await world.admin.revoke_key(await _admin(world), IP, 42)
