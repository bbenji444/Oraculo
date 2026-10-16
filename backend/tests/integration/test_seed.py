"""``make seed`` contra la base de pruebas: crea lo que falta y nunca pisa ediciones."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.seed.cargar_conceptos import read_seed, seed_concepts

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM concepts"))
        conn.execute(text("DELETE FROM audit_log"))


@pytest.fixture
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    _empty(engine)
    yield engine
    _empty(engine)
    engine.dispose()


async def test_segunda_corrida_no_crea_nada(test_engine: AsyncEngine, sync_engine: Engine) -> None:
    first = await seed_concepts(test_engine, read_seed())
    second = await seed_concepts(test_engine, read_seed())

    assert len(first.created) == 5
    assert (second.created, len(second.skipped)) == ((), 5)
    with sync_engine.connect() as conn:
        users = conn.execute(text("SELECT DISTINCT user_id FROM audit_log")).scalars().all()
        assert conn.execute(text("SELECT count(*) FROM concepts")).scalar_one() == 5
    assert users == ["semilla"]


async def test_respeta_un_concepto_editado(test_engine: AsyncEngine, sync_engine: Engine) -> None:
    await seed_concepts(test_engine, read_seed())
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE concepts SET keywords = ARRAY['plagio'] WHERE name = 'Secuestro'")
        )

    await seed_concepts(test_engine, read_seed())

    with sync_engine.connect() as conn:
        keywords = conn.execute(
            text("SELECT keywords FROM concepts WHERE name = 'Secuestro'")
        ).scalar_one()
    assert keywords == ["plagio"]
