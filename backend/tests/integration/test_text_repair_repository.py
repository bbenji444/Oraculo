"""Reparación de Mojibake contra la base de pruebas (F12.1).

Comprueba que el adaptador lee por cursor, guarda los textos reparados y
recalcula ``title_norm`` y ``text_norm``, para que la búsqueda encuentre la
nota con su título correcto.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.text_repair_repository import PostgresStoredText
from app.application.use_cases.repair_text import RepairStoredText
from app.core.config import Settings

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
PREFIX = "https://mojibake.mx/"
BROKEN = "Maru seÃ±alÃ³ corrupciÃ³n ante la FGRðŸŽ¦"
FIXED = "Maru señaló corrupción ante la FGR🎦"


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM articles WHERE url_canonical LIKE :p"), {"p": f"{PREFIX}%"})
        conn.execute(text("DELETE FROM news_index WHERE url LIKE :p"), {"p": f"{PREFIX}%"})


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


def _article(engine: Engine, slug: str, title: str) -> int:
    with engine.begin() as conn:
        article_id = int(
            conn.execute(
                text(
                    "INSERT INTO articles (url_canonical, url_hash, title, title_norm) "
                    "VALUES (:url, md5(:url), :title, 'VIEJO') RETURNING id"
                ),
                {"url": f"{PREFIX}{slug}", "title": title},
            ).scalar_one()
        )
        conn.execute(
            text("INSERT INTO article_texts (article_id, body) VALUES (:id, :body)"),
            {"id": article_id, "body": f"{title}. Cuerpo de la nota."},
        )
        return article_id


def _index_note(engine: Engine, slug: str, title: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "INSERT INTO news_index (source, url, url_hash, title, snippet, "
                    "published_at, text_norm) VALUES ('gdelt_ngrams', :url, md5(:url), "
                    ":title, 'Fragmento', :published, 'VIEJO') RETURNING id"
                ),
                {
                    "url": f"{PREFIX}{slug}",
                    "title": title,
                    "published": datetime(2026, 10, 24, tzinfo=UTC),
                },
            ).scalar_one()
        )


async def test_lee_por_cursor_en_orden(sync_engine: Engine, test_engine: AsyncEngine) -> None:
    first = _article(sync_engine, "a", "Uno")
    second = _article(sync_engine, "b", "Dos")
    store = PostgresStoredText(test_engine)

    rows = await store.fetch("articles", first - 1, 1)
    after = await store.fetch("articles", first, 10)

    assert [r.row_id for r in rows] == [first]
    assert rows[0].fields == {"title": "Uno", "snippet": None, "source_name": None, "summary": None}
    assert second in [r.row_id for r in after]
    assert first not in [r.row_id for r in after]


async def test_repara_y_recalcula_las_columnas_normalizadas(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    broken_article = _article(sync_engine, "rota", BROKEN)
    clean_article = _article(sync_engine, "limpia", "Peñón de los Baños")
    broken_note = _index_note(sync_engine, "rota", BROKEN)
    use_case = RepairStoredText(PostgresStoredText(test_engine))

    for table in ("news_index", "articles", "article_texts"):
        await use_case.run(table, apply=True)

    with sync_engine.connect() as conn:
        article = conn.execute(
            text("SELECT title, title_norm FROM articles WHERE id = :id"), {"id": broken_article}
        ).one()
        untouched = conn.execute(
            text("SELECT title, title_norm FROM articles WHERE id = :id"), {"id": clean_article}
        ).one()
        body = conn.execute(
            text("SELECT body FROM article_texts WHERE article_id = :id"), {"id": broken_article}
        ).scalar_one()
        note = conn.execute(
            text("SELECT title, text_norm FROM news_index WHERE id = :id"), {"id": broken_note}
        ).one()

    assert article.title == FIXED
    assert article.title_norm == "MARU SEÑALO CORRUPCION ANTE LA FGR🎦"
    # Lo que no tenía Mojibake no se toca (ni siquiera su title_norm).
    assert (untouched.title, untouched.title_norm) == ("Peñón de los Baños", "VIEJO")
    assert body == f"{FIXED}. Cuerpo de la nota."
    assert note.title == FIXED
    assert note.text_norm == "MARU SEÑALO CORRUPCION ANTE LA FGR🎦 FRAGMENTO"
