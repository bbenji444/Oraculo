"""Nivel 2 de duplicados en ``articles`` contra la base de pruebas (F12.1b, ADR-0025).

La misma nota que llega con otro link no crea otra fila: se reutiliza la
guardada y, si esa tenía el link de Google News, se cambia al del medio.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.search_repository import PostgresArticleStore
from app.adapters.text.similarity import title_similarity
from app.core.config import Settings
from app.domain.articles import RawArticle
from app.domain.dedupe import dedupe, match_known
from app.domain.queries import Provider

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
NOON = datetime(2026, 10, 22, 18, 0, tzinfo=UTC)
TITLE = "Reportan orden de aprehensión contra empresario por el asesinato de Micky"
GOOGLE = "https://news.google.com/rss/articles/CBMiPruebaDuplicados"
MEDIO = "https://duplicados.mx/mexico/micky"


def _clean(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM articles WHERE url_canonical IN (:a, :b)"), {"a": GOOGLE, "b": MEDIO}
        )


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


def raw(url: str, provider: Provider, published: datetime = NOON) -> RawArticle:
    return RawArticle.create(
        provider=provider,
        provider_rank=1,
        url=url,
        title=TITLE,
        published_at=published,
        source_name="Medio de prueba",
        source_domain="duplicados.mx" if "duplicados" in url else None,
    )


async def test_misma_nota_con_otro_link_reutiliza_y_cambia_al_del_medio(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresArticleStore(test_engine)
    [first] = await store.upsert(dedupe([raw(GOOGLE, Provider.GOOGLE_NEWS_RSS)], title_similarity))

    # Otra búsqueda, un día después: la misma nota llega con el link del medio.
    later = dedupe([raw(MEDIO, Provider.SEARCHAPI, NOON + timedelta(hours=20))], title_similarity)
    [candidates] = await store.known_like(later)
    match = match_known(later[0], candidates, title_similarity)
    later[0].known_id = match.article_id if match else None
    [second] = await store.upsert(later)

    assert second.article_id == first.article_id
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT url_canonical, source_domain FROM articles WHERE url_canonical IN (:a, :b)"
            ),
            {"a": GOOGLE, "b": MEDIO},
        ).all()
    assert [(r.url_canonical, r.source_domain) for r in rows] == [(MEDIO, "duplicados.mx")]


async def test_fuera_de_la_ventana_no_es_candidata(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresArticleStore(test_engine)
    await store.upsert(dedupe([raw(GOOGLE, Provider.GOOGLE_NEWS_RSS)], title_similarity))

    later = dedupe([raw(MEDIO, Provider.SEARCHAPI, NOON + timedelta(days=3))], title_similarity)
    [candidates] = await store.known_like(later)

    assert GOOGLE not in [c.url_canonical for c in candidates]


async def test_si_la_url_ya_existe_gana_esa_nota(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    store = PostgresArticleStore(test_engine)
    [google] = await store.upsert(dedupe([raw(GOOGLE, Provider.GOOGLE_NEWS_RSS)], title_similarity))
    [medio] = await store.upsert(dedupe([raw(MEDIO, Provider.SEARCHAPI)], title_similarity))

    # Ya existen las dos (como los 9 pares medidos): con known_id apuntando a
    # la de Google, la URL del medio sigue ganando y no se toca la otra.
    again = dedupe([raw(MEDIO, Provider.SEARCHAPI)], title_similarity)
    again[0].known_id = google.article_id
    [result] = await store.upsert(again)

    assert result.article_id == medio.article_id
    with sync_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM articles WHERE url_canonical IN (:a, :b)"),
            {"a": GOOGLE, "b": MEDIO},
        ).scalar_one()
    assert count == 2
