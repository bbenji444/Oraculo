"""Historias contra la base de pruebas (F12.1c): ventana por fecha, guardado y migración."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.stories_repository import PostgresStoryStore
from app.adapters.text.similarity import title_similarity, title_token_similarity
from app.application.use_cases.stories import GroupStories
from app.core.config import Settings

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
PREFIX = "https://historias.mx/"
T0 = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


def _clean(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE articles SET story_id = NULL WHERE url_canonical LIKE :p"),
            {"p": f"{PREFIX}%"},
        )
        conn.execute(text("DELETE FROM articles WHERE url_canonical LIKE :p"), {"p": f"{PREFIX}%"})


@pytest.fixture
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    _clean(engine)
    yield engine
    _clean(engine)
    engine.dispose()


def _article(engine: Engine, slug: str, title: str, hours: float) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "INSERT INTO articles (url_canonical, url_hash, title, title_norm, "
                    "published_at) "
                    "VALUES (:url, md5(:url), :title, upper(:title), :at) RETURNING id"
                ),
                {"url": f"{PREFIX}{slug}", "title": title, "at": T0 + timedelta(hours=hours)},
            ).scalar_one()
        )


def _stories(engine: Engine, ids: list[int]) -> dict[int, int | None]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, story_id FROM articles WHERE id = ANY(:ids)"), {"ids": ids}
        ).all()
    return {r.id: r.story_id for r in rows}


async def test_agrupa_con_las_vecinas_y_guarda(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    first = _article(sync_engine, "a", "Balacera en Iztapalapa deja dos muertos y un herido", 0)
    second = _article(
        sync_engine, "b", "Balacera en Iztapalapa deja dos muertos y un herido hoy", 6
    )
    other = _article(sync_engine, "c", "Receta de pollo con salsa de cempasúchil", 3)
    far = _article(sync_engine, "d", "Balacera en Iztapalapa deja dos muertos y un herido", 24 * 10)

    changed = await GroupStories(
        PostgresStoryStore(test_engine), title_similarity, title_token_similarity
    ).run([second, other, far])

    assert changed == 2
    assert _stories(sync_engine, [first, second, other, far]) == {
        first: first,
        second: first,
        other: None,
        far: None,
    }


async def test_la_ventana_trae_solo_notas_cercanas_en_fecha(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    near = _article(sync_engine, "e", "Uno", 0)
    target = _article(sync_engine, "f", "Dos", 30)
    far = _article(sync_engine, "g", "Tres", 24 * 6)

    window = await PostgresStoryStore(test_engine).window([target], timedelta(days=3))

    assert [n.article_id for n in window.targets] == [target]
    neighbors = {n.article_id for n in window.neighbors}
    assert near in neighbors
    assert far not in neighbors
