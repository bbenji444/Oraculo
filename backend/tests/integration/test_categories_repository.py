"""Catálogo de categorías y categoría de cada nota contra la base de pruebas (F12.4)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.categories_repository import PostgresCategoryStore
from app.core.config import Settings
from app.domain.categories import CategoryChoice, other_category

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
PREFIX = "https://categorias.mx/"


def _clean(engine: Engine) -> None:
    with engine.begin() as conn:
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


def _article(
    engine: Engine, slug: str, title: str, summary: str | None, snippet: str | None
) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "INSERT INTO articles (url_canonical, url_hash, title, title_norm, summary, "
                    "snippet) VALUES (:url, md5(:url), :title, upper(:title), :summary, :snippet) "
                    "RETURNING id"
                ),
                {"url": f"{PREFIX}{slug}", "title": title, "summary": summary, "snippet": snippet},
            ).scalar_one()
        )


async def test_el_catalogo_sembrado_tiene_14_y_un_solo_otros(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    categories = await PostgresCategoryStore(test_engine).active_categories()

    assert len(categories) == 14
    assert categories[0].name == "Narcotráfico y delitos contra la salud"
    assert other_category(categories).name == "Otros"
    assert all(c.color is None and c.symbol is None for c in categories)


async def test_pendientes_guardar_y_volver_a_pedir(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresCategoryStore(test_engine)
    armas = _article(sync_engine, "a", "FGR asegura armas", "Aseguran 40 rifles.", "fragmento")
    sin_resumen = _article(sync_engine, "b", "Detienen a exfiscal", None, "Del medio.")
    categories = await store.active_categories()
    weapons = next(c for c in categories if c.name == "Armas y explosivos")

    pending = await store.pending_notes([armas, sin_resumen], "classify_v1")
    await store.save([CategoryChoice(armas, weapons, "tráfico de armas")], "classify_v1")
    again = await store.pending_notes([armas, sin_resumen], "classify_v1")
    newer = await store.pending_notes([armas, sin_resumen], "classify_v2")

    # Sin resumen de la IA se usa el fragmento del medio.
    assert [(n.article_id, n.summary) for n in pending] == [
        (armas, "Aseguran 40 rifles."),
        (sin_resumen, "Del medio."),
    ]
    assert [n.article_id for n in again] == [sin_resumen]
    # Otra versión del prompt: se vuelve a clasificar.
    assert [n.article_id for n in newer] == [armas, sin_resumen]
    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT category_id, category_raw, category_version FROM articles WHERE id = :id"),
            {"id": armas},
        ).one()
    assert tuple(row) == (weapons.category_id, "tráfico de armas", "classify_v1")
