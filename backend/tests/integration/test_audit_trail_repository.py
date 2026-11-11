"""Leer la bitácora contra la base de pruebas (``PostgresAuditTrail``).

Revisa que la consulta pagine por ``id`` sin saltarse ni repetir registros,
que el grupo compare el tema entero (el ``_`` de ``access_key`` no es un
comodín), que filtre por persona y que traiga el nombre desde ``users``.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.audit_trail_repository import PostgresAuditTrail
from app.core.config import Settings
from app.domain.audit_trail import AuditGroup, AuditQuery

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
ANA = "prueba-bitacora-ana"
NADIE = "prueba-bitacora-consola"
# Una acción que solo empataría con LIKE 'access_key%' por el comodín «_».
LOOKALIKE = "accessXkey.revealed"


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM audit_log WHERE user_id IN (:a, :n)"), {"a": ANA, "n": NADIE}
        )
        conn.execute(text("DELETE FROM users WHERE username = :a"), {"a": ANA})


@pytest.fixture
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    _empty(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (username, display_name, created_by) "
                "VALUES (:a, 'Ana Bitácora', 'prueba')"
            ),
            {"a": ANA},
        )
        for who, action, ip in (
            (ANA, "auth.login", "10.244.0.7"),
            (ANA, "access_key.revealed", "10.244.0.7"),
            (NADIE, "user.password_reset", None),
            (ANA, "search.finished", "10.244.0.7"),
            (NADIE, LOOKALIKE, None),
        ):
            conn.execute(
                text(
                    "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
                    "VALUES (:w, :a, split_part(:a, '.', 1), '1', "
                    "jsonb_build_object('llave', 'orc_live_a1b2c3d4…'), CAST(:ip AS inet))"
                ),
                {"w": who, "a": action, "ip": ip},
            )
    yield engine
    _empty(engine)
    engine.dispose()


async def _ours(trail: PostgresAuditTrail, query: AuditQuery) -> list[tuple[str, str]]:
    """Solo los registros de esta prueba: la base de pruebas trae otros."""
    events = await trail.events(query, 1000)
    return [(e.actor, e.action) for e in events if e.actor in (ANA, NADIE)]


async def test_lee_de_lo_nuevo_a_lo_viejo_con_nombre_e_ip(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    trail = PostgresAuditTrail(test_engine)

    events = [e for e in await trail.events(AuditQuery(), 1000) if e.actor in (ANA, NADIE)]

    assert [e.action for e in events] == [
        LOOKALIKE,
        "search.finished",
        "user.password_reset",
        "access_key.revealed",
        "auth.login",
    ]
    revealed = events[3]
    assert (revealed.actor_name, revealed.ip) == ("Ana Bitácora", "10.244.0.7")
    assert revealed.payload == {"llave": "orc_live_a1b2c3d4…"}
    assert (events[2].actor_name, events[2].ip) == (None, None)


async def test_el_grupo_compara_el_tema_entero(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    trail = PostgresAuditTrail(test_engine)

    access = await _ours(trail, AuditQuery(AuditGroup.ACCESS))
    only_ana = await _ours(trail, AuditQuery(actor=ANA))

    assert access == [
        (NADIE, "user.password_reset"),
        (ANA, "access_key.revealed"),
        (ANA, "auth.login"),
    ]
    assert [a for _, a in only_ana] == ["search.finished", "access_key.revealed", "auth.login"]


async def test_el_cursor_no_salta_ni_repite(sync_engine: Engine, test_engine: AsyncEngine) -> None:
    trail = PostgresAuditTrail(test_engine)
    query = AuditQuery(actor=ANA)

    first = await trail.events(query, 2)
    rest = await trail.events(AuditQuery(actor=ANA, before=first[-1].event_id), 2)

    assert [e.action for e in first + rest] == [
        "search.finished",
        "access_key.revealed",
        "auth.login",
    ]
