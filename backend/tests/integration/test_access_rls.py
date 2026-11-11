"""Seguridad por filas, personas, credenciales y llaves contra la base y Redis de pruebas.

ADR-0042 (llaves, roles y RLS) y ADR-0043 (contraseña y código de 6 dígitos).

Usa el mismo engine que la API (``create_api_engine``): cada transacción le
dice a PostgreSQL quién pregunta, y las políticas de la migración 0039
deciden qué filas ve. Así se prueba que la separación la hace la base,
aunque una ruta de la API olvidara filtrar.
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.cache.redis_sessions import (
    RedisLoginLimiter,
    RedisLoginTicketStore,
    RedisSessionStore,
)
from app.adapters.persistence.access_repository import PostgresAccessStore
from app.adapters.persistence.access_scope import as_system, as_user, create_api_engine
from app.adapters.persistence.search_repository import PostgresSearchStore
from app.adapters.security.secret_box import AesGcmSecretBox
from app.application.audit import Actor, AuditEntry
from app.application.ports.access import (
    LoginTicket,
    NewKeyRow,
    NewUser,
    SessionData,
    UserChanges,
)
from app.application.ports.search_reads import HistoryScope
from app.application.ports.search_store import NewSearch
from app.core.config import Settings
from app.domain.access import AuthUser, Role, key_digest, new_key
from app.domain.credentials import hash_password, verify_password
from app.domain.errors import UsernameTakenError
from app.domain.queries import Provider
from tests.integration.geo_fixture import load_fixture_catalog

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
ANA = AuthUser(901, "rls-ana", "Ana", Role.USER)
PEPE = AuthUser(902, "rls-pepe", "Pepe", Role.USER)
JEFA = AuthUser(903, "rls-jefa", "Jefa", Role.SUPERUSER)
PEPPER = b"pimienta-de-prueba-con-mas-de-32-caracteres"
AUDIT = AuditEntry(Actor("rls-prueba"), "prueba", {})


def _clean(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM searches WHERE user_id LIKE 'rls-%'"))
        conn.execute(text("DELETE FROM users WHERE username LIKE 'rls-%'"))
        conn.execute(text("DELETE FROM audit_log WHERE user_id LIKE 'rls-%'"))


@pytest.fixture(scope="module")
def catalog(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    yield engine
    engine.dispose()


@pytest.fixture
def clean(catalog: Engine) -> Iterator[Engine]:
    _clean(catalog)
    yield catalog
    _clean(catalog)


@pytest.fixture
async def api_engine(settings: Settings, clean: Engine) -> AsyncIterator[AsyncEngine]:
    engine = create_api_engine(settings.database_url(test=True))
    yield engine
    await engine.dispose()


async def _search(test_engine: AsyncEngine, owner: str) -> UUID:
    """Una búsqueda guardada como el sistema (como lo hace el worker)."""
    async with test_engine.connect() as conn:
        region = (await conn.execute(text("SELECT id FROM regions WHERE code = '09'"))).scalar_one()
    return await PostgresSearchStore(test_engine).create(
        NewSearch(
            user_id=owner,
            region_id=region,
            date_from=date(2026, 11, 1),
            date_to=date(2026, 11, 2),
            concepts=(),
            queries_planned=1,
            credits_estimated=0,
            providers=(Provider.LOCAL_INDEX,),
        )
    )


async def _visible(engine: AsyncEngine, sql: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(sql))).scalar_one())


async def test_cada_persona_ve_solo_sus_busquedas(
    test_engine: AsyncEngine, api_engine: AsyncEngine
) -> None:
    mine = await _search(test_engine, ANA.username)
    other = await _search(test_engine, PEPE.username)
    store = PostgresSearchStore(api_engine)
    count = "SELECT count(*) FROM searches WHERE user_id LIKE 'rls-%'"

    with as_user(ANA):
        ana_sees = await _visible(api_engine, count)
        # Aunque pida «todas», la base no le da las de Pepe.
        everyone = await store.history(HistoryScope(None), None, 50)
        assert await store.search_detail(other) is None
        assert await store.search_detail(mine) is not None
    with as_user(JEFA):
        boss_sees = await _visible(api_engine, count)

    assert ana_sees == 1
    assert {d.search_id for d in everyone} == {mine}
    assert boss_sees == 2


async def test_sin_persona_la_api_no_ve_nada(
    test_engine: AsyncEngine, api_engine: AsyncEngine
) -> None:
    await _search(test_engine, ANA.username)

    # Ni búsquedas ni personas: el engine de la API nace «anonymous».
    assert await _visible(api_engine, "SELECT count(*) FROM searches") == 0
    assert await _visible(api_engine, "SELECT count(*) FROM users") == 0
    assert await _visible(api_engine, "SELECT count(*) FROM search_concepts") == 0
    # El worker y los comandos (engine sin contexto) siguen viendo todo.
    assert await _visible(test_engine, "SELECT count(*) FROM searches") >= 1


async def test_nadie_guarda_busquedas_a_nombre_de_otro(api_engine: AsyncEngine) -> None:
    with as_user(ANA), pytest.raises(DBAPIError, match="row-level security"):
        async with api_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO searches (user_id, region_id, date_from, date_to) "
                    "SELECT 'rls-pepe', id, '2026-11-01', '2026-11-02' FROM regions LIMIT 1"
                )
            )


async def test_ana_no_borra_ni_cambia_las_de_pepe(
    test_engine: AsyncEngine, api_engine: AsyncEngine
) -> None:
    other = await _search(test_engine, PEPE.username)

    with as_user(ANA):
        async with api_engine.begin() as conn:
            changed = await conn.execute(
                text("UPDATE searches SET deleted_at = now() WHERE id = :id"), {"id": other}
            )

    assert changed.rowcount == 0
    async with test_engine.connect() as conn:
        deleted = await conn.scalar(
            text("SELECT deleted_at FROM searches WHERE id = :id"), {"id": other}
        )
    assert deleted is None


async def test_un_usuario_normal_no_ve_personas_ni_llaves(api_engine: AsyncEngine) -> None:
    with as_user(JEFA):
        await PostgresAccessStore(api_engine).create_user(
            NewUser(ANA.username, "Ana", None, Role.USER), AUDIT
        )

    with as_user(ANA):
        users = await _visible(api_engine, "SELECT count(*) FROM users")
        keys = await _visible(api_engine, "SELECT count(*) FROM access_keys")

    assert (users, keys) == (0, 0)


async def test_personas_y_llaves_de_punta_a_punta(api_engine: AsyncEngine) -> None:
    store = PostgresAccessStore(api_engine)
    key = new_key()
    with as_user(JEFA):
        ana = await store.create_user(NewUser(ANA.username, "Ana", "ana@x.mx", Role.USER), AUDIT)
        with pytest.raises(UsernameTakenError):
            await store.create_user(NewUser(ANA.username, "Otra", None, Role.USER), AUDIT)
        info = await store.create_key(
            NewKeyRow(
                ana.user_id,
                key.public_id,
                key_digest(key.full, PEPPER),
                "Laptop",
                datetime.now(UTC) + timedelta(days=30),
            ),
            AUDIT,
        )
        listed = await store.get_user(ana.user_id)
    # Al entrar todavía no se sabe quién es: la búsqueda de la llave va como sistema.
    found = await store.find_key(key.public_id)
    await store.mark_key_used(info.key_id, "192.168.0.50")
    with as_user(JEFA):
        updated = await store.update_user(
            ana.user_id, UserChanges(display_name="Ana López", email=""), AUDIT
        )
        revoked = await store.revoke_key(info.key_id, AUDIT)
        again = await store.revoke_key(info.key_id, AUDIT)
        [stored_key] = await store.user_keys(ana.user_id)
        after = await store.get_user(ana.user_id)

    assert listed is not None and listed.active_keys == 1
    assert found is not None
    assert found.user.username == ANA.username
    assert found.key_hash == key_digest(key.full, PEPPER)
    assert key.full not in found.key_hash
    assert updated is not None and (updated.display_name, updated.email) == ("Ana López", None)
    assert revoked is not None and again is not None
    assert revoked.revoked_at == again.revoked_at
    assert stored_key.last_used_ip == "192.168.0.50"
    assert after is not None and after.active_keys == 0
    assert after.last_seen_at is not None


async def test_la_llave_completa_no_queda_en_la_base(
    api_engine: AsyncEngine, test_engine: AsyncEngine
) -> None:
    store = PostgresAccessStore(api_engine)
    key = new_key()
    with as_user(JEFA):
        ana = await store.create_user(NewUser(ANA.username, "Ana", None, Role.USER), AUDIT)
        await store.create_key(
            NewKeyRow(ana.user_id, key.public_id, key_digest(key.full, PEPPER), "", None), AUDIT
        )

    async with test_engine.connect() as conn:
        dump = await conn.scalar(
            text(
                "SELECT string_agg(k::text, ' ') FROM access_keys k "
                "JOIN users u ON u.id = k.user_id WHERE u.username = :u"
            ),
            {"u": ANA.username},
        )
        logged = await conn.scalar(
            text("SELECT string_agg(payload::text, ' ') FROM audit_log WHERE user_id LIKE 'rls-%'")
        )
    secret = key.full.split("_")[-1]
    assert dump is not None and secret not in dump
    assert secret not in (logged or "")


async def test_el_contexto_no_se_filtra_entre_peticiones(
    test_engine: AsyncEngine, api_engine: AsyncEngine
) -> None:
    await _search(test_engine, PEPE.username)
    count = "SELECT count(*) FROM searches WHERE user_id LIKE 'rls-%'"

    with as_system():
        system_sees = await _visible(api_engine, count)
    # Misma conexión del pool, ya sin contexto: vuelve a «anonymous».
    after = await _visible(api_engine, count)

    assert (system_sees, after) == (1, 0)


async def test_sesiones_en_redis(test_redis: Redis) -> None:
    sessions = RedisSessionStore(test_redis)
    now = datetime.now(UTC)
    laptop = await sessions.create(SessionData(ANA, 1, now, now), 60, 3600)
    casa = await sessions.create(SessionData(ANA, 2, now, now), 60, 3600)

    stored = await sessions.get(laptop, 60)
    raw_keys = [k.decode() for k in await test_redis.keys("monitor:sesion:*")]
    closed = await sessions.delete_for_user(ANA.user_id, key_id=1)

    assert stored is not None and stored.user == ANA
    # En Redis queda la huella, no el valor de la cookie.
    assert all(laptop not in k and casa not in k for k in raw_keys)
    assert closed == 1
    assert await sessions.get(laptop, 60) is None
    assert await sessions.get(casa, 60) is not None
    assert await sessions.delete_for_user(ANA.user_id) == 1


async def test_freno_de_intentos_en_redis(test_redis: Redis) -> None:
    limiter = RedisLoginLimiter(test_redis, max_failures=2, window_seconds=30)
    ip = "10.9.9.9"
    await limiter.clear(ip)

    await limiter.failure(ip)
    first = await limiter.blocked(ip)
    await limiter.failure(ip)
    second = await limiter.blocked(ip)
    ttl = await test_redis.ttl("monitor:fallos-llave:10.9.9.9")
    await limiter.clear(ip)

    assert (first, second) == (False, True)
    assert 0 < ttl <= 30
    assert not await limiter.blocked(ip)


async def test_credenciales_de_punta_a_punta(api_engine: AsyncEngine) -> None:
    store = PostgresAccessStore(api_engine)
    with as_user(JEFA):
        ana = await store.create_user(NewUser(ANA.username, "Ana", None, Role.USER), AUDIT)
    box = AesGcmSecretBox(PEPPER)
    secret = box.seal("JBSWY3DPEHPK3PXP")
    lock = datetime.now(UTC) + timedelta(minutes=15)

    # Todo esto pasa antes de saber quién es la persona (como «anonymous»).
    before = await store.find_credentials(ANA.username)
    await store.set_password(ana.user_id, hash_password("Clave-segura-2026"), False, AUDIT)
    await store.login_failed(ana.user_id, 5, lock)
    locked = await store.credentials(ana.user_id)
    await store.set_totp(ana.user_id, secret, AUDIT)
    first = await store.use_totp_counter(ana.user_id, 100)
    repeated = await store.use_totp_counter(ana.user_id, 100)
    older = await store.use_totp_counter(ana.user_id, 99)
    await store.login_succeeded(ana.user_id, "192.168.0.50")
    after = await store.credentials(ana.user_id)
    with as_user(JEFA):
        listed = await store.get_user(ana.user_id)

    assert before is not None and before.password_hash is None and before.must_change_password
    assert locked is not None and (locked.failed_logins, locked.locked_until) == (5, lock)
    assert (first, repeated, older) == (True, False, False)
    assert after is not None
    assert verify_password("Clave-segura-2026", after.password_hash)
    assert (after.failed_logins, after.locked_until, after.totp_last_counter) == (0, None, 100)
    assert after.totp_secret == secret and "JBSWY3DPEHPK3PXP" not in secret
    assert box.open(after.totp_secret) == "JBSWY3DPEHPK3PXP"
    assert listed is not None
    assert (listed.has_password, listed.must_change_password, listed.totp_enrolled) == (
        True,
        False,
        True,
    )
    await store.set_totp(ana.user_id, None, AUDIT)
    reset = await store.credentials(ana.user_id)
    assert reset is not None and reset.totp_secret is None and reset.totp_last_counter is None


async def test_la_contrasena_y_el_secreto_no_quedan_en_claro(
    api_engine: AsyncEngine, test_engine: AsyncEngine
) -> None:
    store = PostgresAccessStore(api_engine)
    with as_user(JEFA):
        ana = await store.create_user(NewUser(ANA.username, "Ana", None, Role.USER), AUDIT)
    await store.set_password(ana.user_id, hash_password("Clave-secreta-2026"), False, AUDIT)
    await store.set_totp(ana.user_id, AesGcmSecretBox(PEPPER).seal("SECRETO2026TOTP"), AUDIT)

    async with test_engine.connect() as conn:
        row = await conn.scalar(
            text("SELECT u::text FROM users u WHERE username = :u"), {"u": ANA.username}
        )

    assert row is not None
    assert "Clave-secreta-2026" not in row
    assert "SECRETO2026TOTP" not in row


async def test_ingreso_a_medias_en_redis(test_redis: Redis) -> None:
    tickets = RedisLoginTicketStore(test_redis)
    ticket = LoginTicket(901, ANA.username, True, True)

    token = await tickets.create(ticket, 30)
    stored = await tickets.get(token)
    await tickets.save(token, replace(ticket, attempts=2, pending_secret="v1:abc"), 30)
    updated = await tickets.get(token)
    names = [k.decode() for k in await test_redis.keys("monitor:ingreso:*")]
    ttl = max([await test_redis.ttl(n) for n in names] or [0])
    await tickets.delete(token)

    assert stored == ticket
    assert updated is not None and (updated.attempts, updated.pending_secret) == (2, "v1:abc")
    assert all(token not in n for n in names)
    assert 0 < ttl <= 30
    assert await tickets.get(token) is None


def test_el_secreto_cifrado_no_se_puede_alterar() -> None:
    box = AesGcmSecretBox(PEPPER)
    sealed = box.seal("JBSWY3DPEHPK3PXP")
    tampered = sealed[:-4] + ("AAAA" if not sealed.endswith("AAAA") else "BBBB")

    assert box.seal("JBSWY3DPEHPK3PXP") != sealed
    with pytest.raises(ValueError, match="alterado"):
        box.open(tampered)
    with pytest.raises(ValueError, match="otra pimienta"):
        AesGcmSecretBox(b"otra-pimienta-de-mas-de-32-caracteres!!").open(sealed)
    with pytest.raises(ValueError, match="formato"):
        box.open("v9:xyz")
