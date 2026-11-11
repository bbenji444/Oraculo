"""Sesiones, llaves de sistema y administración de accesos (ADR-0042/0043), sin base."""

from dataclasses import replace

import pytest

from app.application.ports.access import SessionData, UserChanges
from app.domain.access import MAX_ACTIVE_KEYS_PER_USER, AuthUser, Role
from app.domain.credentials import verify_password
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
from tests.unit.fake_access import POLICY, AccessWorld, access_world

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


async def _session(world: AccessWorld, user_id: int) -> str:
    """Una sesión de contraseña ya abierta (como la que deja PasswordLogin)."""
    creds = await world.store.credentials(user_id)
    assert creds is not None
    now = world.clock()
    return await world.sessions.create(
        SessionData(creds.user, None, now, now), POLICY.idle_seconds, POLICY.max_seconds
    )


# --- Llaves de sistema (Bearer) ------------------------------------------------------


async def test_la_llave_de_sistema_reconoce_a_su_dueno(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    key = await _key_for(world, ana)

    user = await world.auth.from_bearer(key, IP)

    assert (user.username, user.role) == ("ana", Role.USER)
    assert world.sessions.data == {}
    assert world.store.used == [(1, IP)]


async def test_la_base_nunca_guarda_la_llave_completa(world: AccessWorld) -> None:
    key = await _key_for(world, 1)

    [stored] = world.store.keys.values()

    assert key not in stored.key_hash
    assert key not in repr(stored.info)
    assert all(key not in repr(e) for e in world.store.events)


@pytest.mark.parametrize("bad", ["", "hola", "orc_live_ABCDEFGH_" + "x" * 40])
async def test_una_llave_falsa_no_sirve_y_queda_en_la_bitacora(
    world: AccessWorld, bad: str
) -> None:
    with pytest.raises(AuthenticationRequiredError, match="no es válida"):
        await world.auth.from_bearer(bad, IP)

    assert world.store.events[-1][0].action == "auth.login_failed"
    assert world.limiter.failures[IP] == 1


async def test_parte_publica_correcta_con_secreto_falso(world: AccessWorld) -> None:
    key = await _key_for(world, 1)
    forged = key[:-1] + ("A" if key[-1] != "A" else "B")

    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_bearer(forged, IP)
    # Quien falla no se sabe: la bitácora no le atribuye el intento a benji.
    assert world.store.events[-1][0].actor.user_id == "anonimo"


async def test_llave_revocada_vencida_o_de_persona_desactivada(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    revoked = await _key_for(world, ana)
    await world.admin.revoke_key(await _admin(world), IP, 1)
    expiring = await _key_for(world, ana, days=1)
    world.clock.advance(days=2)

    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_bearer(revoked, IP)
    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_bearer(expiring, IP)

    pepe = world.store.add_user("pepe")
    valid = await _key_for(world, pepe)
    await world.admin.update_user(await _admin(world), IP, pepe, UserChanges(is_active=False))
    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_bearer(valid, IP)


async def test_demasiados_intentos_bloquean_la_ip(world: AccessWorld) -> None:
    key = await _key_for(world, 1)
    for _ in range(world.limiter.max):
        with pytest.raises(AuthenticationRequiredError):
            await world.auth.from_bearer("mala", IP)

    with pytest.raises(TooManyAttemptsError):
        await world.auth.from_bearer(key, IP)
    assert (await world.auth.from_bearer(key, "10.0.0.9")).username == "benji"


# --- Sesiones (el token interno) ----------------------------------------------------------


async def test_la_sesion_dura_a_lo_mas_30_dias(world: AccessWorld) -> None:
    token = await _session(world, 1)
    world.clock.advance(days=29)
    assert (await world.auth.from_session(token)).username == "benji"

    world.clock.advance(days=1, seconds=1)
    with pytest.raises(AuthenticationRequiredError, match="sesión terminó"):
        await world.auth.from_session(token)
    assert token not in world.sessions.data


async def test_la_sesion_revisa_a_la_persona_cada_5_minutos(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    token = await _session(world, ana)
    # Se desactiva «por fuera» (sin cerrar sesiones), como si fallara Redis.
    world.store.users[ana] = replace(world.store.users[ana], is_active=False)

    world.clock.advance(minutes=4)
    assert (await world.auth.from_session(token)).username == "ana"
    world.clock.advance(minutes=2)
    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_session(token)


async def test_la_revision_refresca_nombre_y_rol(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    token = await _session(world, ana)
    world.store.users[ana] = replace(
        world.store.users[ana], display_name="Ana López", role=Role.SUPERUSER
    )
    world.clock.advance(minutes=6)

    user = await world.auth.from_session(token)

    assert (user.display_name, user.role) == ("Ana López", Role.SUPERUSER)


async def test_salir_cierra_la_sesion(world: AccessWorld) -> None:
    token = await _session(world, 1)

    await world.auth.logout(token)

    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_session(token)


async def test_otro_modulo_pregunta_de_quien_es_un_token(world: AccessWorld) -> None:
    token = await _session(world, 1)

    found = await world.auth.introspect(token)
    missing = await world.auth.introspect("token-inventado")

    assert found is not None and found.username == "benji"
    assert missing is None


# --- Administración ---------------------------------------------------------------------


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
    with pytest.raises(ForbiddenError):
        await world.admin.reset_password(ana, IP, 1)
    with pytest.raises(ForbiddenError):
        await world.admin.reset_totp(ana, IP, 1)


async def test_alta_con_contrasena_temporal(world: AccessWorld) -> None:
    admin = await _admin(world)

    created = await world.admin.create_user(
        admin,
        IP,
        username=" Ana.Lopez ",
        display_name="Ana  López",
        email="ANA@x.mx",
        role=Role.USER,
    )

    account = created.account
    assert (account.username, account.display_name, account.email) == (
        "ana.lopez",
        "Ana López",
        "ana@x.mx",
    )
    assert (account.has_password, account.must_change_password) == (True, True)
    assert account.totp_enrolled is False
    assert len(created.temporary_password) == 16
    creds = world.store.creds[account.user_id]
    assert created.temporary_password not in (creds.password_hash or "")
    assert verify_password(created.temporary_password, creds.password_hash)
    assert all(created.temporary_password not in repr(e) for e in world.store.events)
    with pytest.raises(UsernameTakenError):
        await world.admin.create_user(
            admin, IP, username="ana.lopez", display_name="Otra", email=None, role=Role.USER
        )


async def test_restablecer_contrasena_cierra_sesiones_y_conserva_el_codigo(
    world: AccessWorld,
) -> None:
    ana = world.store.add_user("ana")
    world.store.creds[ana].totp_secret = "sellado:XYZ"
    token = await _session(world, ana)

    temporary = await world.admin.reset_password(await _admin(world), IP, ana)

    assert verify_password(temporary, world.store.creds[ana].password_hash)
    assert world.store.creds[ana].must_change is True
    assert world.store.creds[ana].totp_secret == "sellado:XYZ"
    assert token not in world.sessions.data
    assert world.store.events[-1][0].action == "user.password_reset"


async def test_reiniciar_autenticador_cierra_sesiones(world: AccessWorld) -> None:
    ana = world.store.add_user("ana")
    world.store.creds[ana].totp_secret = "sellado:XYZ"
    token = await _session(world, ana)

    await world.admin.reset_totp(await _admin(world), IP, ana)

    assert world.store.creds[ana].totp_secret is None
    assert token not in world.sessions.data
    with pytest.raises(UserNotFoundError):
        await world.admin.reset_totp(await _admin(world), IP, 99)
    with pytest.raises(UserNotFoundError):
        await world.admin.reset_password(await _admin(world), IP, 99)


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
    token = await _session(world, ana)

    await world.admin.update_user(admin, IP, ana, UserChanges(role=Role.SUPERUSER))

    with pytest.raises(AuthenticationRequiredError):
        await world.auth.from_session(token)


async def test_cambiar_solo_el_nombre_no_cierra_sesiones(world: AccessWorld) -> None:
    admin = await _admin(world)
    ana = world.store.add_user("ana")
    token = await _session(world, ana)

    updated = await world.admin.update_user(admin, IP, ana, UserChanges(display_name="Ana L."))

    assert updated.display_name == "Ana L."
    assert token in world.sessions.data


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
    await _key_for(world, ana)
    await _key_for(world, ana)
    creds = await world.store.credentials(ana)
    assert creds is not None
    now = world.clock()
    laptop = await world.sessions.create(SessionData(creds.user, 1, now, now), 60, 60)
    casa = await world.sessions.create(SessionData(creds.user, 2, now, now), 60, 60)

    revoked = await world.admin.revoke_key(admin, IP, 1)

    assert revoked.revoked_at is not None
    assert laptop not in world.sessions.data
    assert casa in world.sessions.data


async def test_no_puedes_revocar_tu_unica_llave(world: AccessWorld) -> None:
    await _key_for(world, 1)

    with pytest.raises(AccessRuleError, match="única"):
        await world.admin.revoke_key(await _admin(world), IP, 1)
    await _key_for(world, 1)
    assert (await world.admin.revoke_key(await _admin(world), IP, 1)).revoked_at is not None


async def test_revocar_una_llave_que_no_existe(world: AccessWorld) -> None:
    with pytest.raises(AccessKeyNotFoundError):
        await world.admin.revoke_key(await _admin(world), IP, 42)


async def test_borrar_a_una_persona(world: AccessWorld) -> None:
    admin = await _admin(world)
    ana = world.store.add_user("ana")
    await _key_for(world, ana)
    token = await _session(world, ana)

    await world.admin.delete_user(admin, IP, ana)

    assert await world.store.get_user(ana) is None
    assert all(k.info.revoked_at is not None for k in world.store.keys.values())
    assert token not in world.sessions.data
    assert world.store.events[-1][0].action == "user.deleted"
    with pytest.raises(UserNotFoundError):
        await world.admin.delete_user(admin, IP, ana)


async def test_nadie_se_borra_a_si_mismo_ni_al_ultimo_superusuario(world: AccessWorld) -> None:
    admin = await _admin(world)
    otro = world.store.add_user("otro", Role.SUPERUSER)
    otro_admin = AuthUser(otro, "otro", "Otro", Role.SUPERUSER)

    with pytest.raises(AccessRuleError, match="ti mismo"):
        await world.admin.delete_user(admin, IP, 1)
    await world.admin.update_user(otro_admin, IP, 1, UserChanges(is_active=False))
    with pytest.raises(AccessRuleError, match="al menos un superusuario"):
        await world.admin.delete_user(admin, IP, otro)


async def test_un_usuario_normal_no_borra(world: AccessWorld) -> None:
    ana = AuthUser(world.store.add_user("ana"), "ana", "Ana", Role.USER)

    with pytest.raises(ForbiddenError):
        await world.admin.delete_user(ana, IP, 1)
