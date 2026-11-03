"""``make seed`` contra la base de pruebas: crea lo que falta y nunca pisa ediciones."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.seed.cargar_conceptos import (
    apply_rules,
    read_rules,
    read_seed,
    read_topics,
    seed_concepts,
    seed_topics,
)

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

    assert len(first.created) == 1
    assert (second.created, len(second.skipped)) == ((), 1)
    with sync_engine.connect() as conn:
        users = conn.execute(text("SELECT DISTINCT user_id FROM audit_log")).scalars().all()
        assert conn.execute(text("SELECT count(*) FROM concepts")).scalar_one() == 1
    assert users == ["semilla"]


async def test_respeta_un_concepto_editado(test_engine: AsyncEngine, sync_engine: Engine) -> None:
    await seed_concepts(test_engine, read_seed())
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE concepts SET keywords = ARRAY['FGR'] WHERE name_norm LIKE 'FISCALIA%'")
        )

    await seed_concepts(test_engine, read_seed())

    with sync_engine.connect() as conn:
        keywords = conn.execute(
            text("SELECT keywords FROM concepts WHERE name_norm LIKE 'FISCALIA%'")
        ).scalar_one()
    assert keywords == ["FGR"]


async def test_pone_la_regla_fgr_federal_sin_pisar_una_cambiada(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    # F12.6, ADR-0030: una instalación nueva arranca con la regla puesta.
    await seed_concepts(test_engine, read_seed())
    await apply_rules(test_engine, read_rules())
    with sync_engine.connect() as conn:
        rule = conn.execute(text("SELECT relevance_rule FROM concepts")).scalar_one()
    assert rule == "fgr_federal"


# --- Temas generales de las subdivisiones (02/11/2026) ---


async def test_crea_un_tema_por_subdivision_ligado_y_con_su_color(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    first = await seed_topics(test_engine, read_topics())
    second = await seed_topics(test_engine, read_topics())

    assert (len(first.created), first.skipped, first.missing) == (14, (), ())
    assert (second.created, len(second.skipped)) == ((), 14)
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT k.name, k.color, c.name AS category, c.color AS category_color "
                "FROM concepts k JOIN categories c ON c.id = k.category_id"
            )
        ).all()
        orphans = conn.execute(
            text("SELECT count(*) FROM concepts WHERE category_id IS NULL")
        ).scalar_one()
    assert len(rows) == 14
    assert all(r.name == r.category and r.color == r.category_color for r in rows)
    assert "Otros" not in {r.category for r in rows}
    assert orphans == 0


async def test_respeta_un_tema_editado(test_engine: AsyncEngine, sync_engine: Engine) -> None:
    await seed_topics(test_engine, read_topics())
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE concepts SET keywords = ARRAY['homicidio'] WHERE name_norm = 'HOMICIDIO'")
        )

    await seed_topics(test_engine, read_topics())

    with sync_engine.connect() as conn:
        keywords = conn.execute(
            text("SELECT keywords FROM concepts WHERE name_norm = 'HOMICIDIO'")
        ).scalar_one()
    assert keywords == ["homicidio"]
