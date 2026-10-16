"""Búsqueda en el índice local contra la base de pruebas (ADR-0013)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.news_index_repository import PostgresNewsIndex
from app.adapters.providers.local_index import LocalIndexProvider, word_pattern
from app.core.config import Settings
from app.domain.news_index import NewsItem
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider, QueryPlace

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
# Del 10 al 16 de octubre en hora de la CDMX: del 10/10 06:00 al 17/10 06:00 UTC.
WINDOW = DateWindow.between(date(2026, 10, 10), date(2026, 10, 16))
IZTAPALAPA = QueryPlace(("Iztapalapa",), (), MEXICO)
JALISCO = QueryPlace(("Jalisco",), (), MEXICO, "14")
NOON = datetime(2026, 10, 15, 18, 0, tzinfo=UTC)


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM news_index"))


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


def note(slug: str, title: str, at: datetime = NOON, states: tuple[str, ...] = ()) -> NewsItem:
    return NewsItem.create(
        source="gdelt_gkg",
        url=f"https://medio.mx/{slug}",
        title=title,
        published_at=at,
        gdelt_states=states,
    )


NOTES = [
    note("a", "Hackeo a la alcaldía Iztapalapa"),
    note("plural", "Hackeos en Iztapalapa"),
    note("curso", "Curso contra el hackeo en Iztapalapa"),
    note("gdl", "Hackeo en dependencia de Guadalajara", states=("14",)),
    note("penon", "Hackeo en el Peñón de los Baños"),
    note("vieja", "Hackeo en Iztapalapa", at=datetime(2026, 9, 1, tzinfo=UTC)),
    # 23:30 del 16/10 en la CDMX: dentro. 00:00 del 17/10: fuera.
    note("borde", "Hackeo nocturno en Iztapalapa", at=datetime(2026, 10, 17, 5, 30, tzinfo=UTC)),
    note("fuera", "Hackeo de madrugada en Iztapalapa", at=datetime(2026, 10, 17, 6, tzinfo=UTC)),
]


def query(
    place: QueryPlace | None,
    keywords: tuple[str, ...] = ("hackeo",),
    exclude: tuple[str, ...] = ("curso",),
) -> PlannedQuery:
    return PlannedQuery(
        Provider.LOCAL_INDEX, "t", keywords, MEXICO, "es", WINDOW, 0, exclude, place
    )


@pytest.fixture
async def provider(sync_engine: Engine, test_engine: AsyncEngine) -> LocalIndexProvider:
    await PostgresNewsIndex(test_engine).add(NOTES)
    return LocalIndexProvider(test_engine)


def slugs(response_urls: list[str]) -> list[str]:
    return [url.rsplit("/", 1)[-1] for url in response_urls]


async def test_palabra_completa_lugar_exclusiones_y_fechas(provider: LocalIndexProvider) -> None:
    response = await provider.search(query(IZTAPALAPA))

    # Fuera: "Hackeos" (otra palabra), "Curso" (exclusión), Guadalajara (otro
    # lugar), la vieja y la de las 00:00 del 17/10. Más recientes primero.
    assert slugs([a.url for a in response.articles]) == ["borde", "a"]
    assert [a.provider_rank for a in response.articles] == [1, 2]
    assert response.http_status == 200
    assert response.params["lugar"] == "IZTAPALAPA"


async def test_un_estado_acepta_notas_que_gdelt_ubico_ahi(provider: LocalIndexProvider) -> None:
    response = await provider.search(query(JALISCO))

    assert slugs([a.url for a in response.articles]) == ["gdl"]
    assert response.articles[0].raw["gdelt_states"] == ["14"]


async def test_mexico_completo_no_filtra_lugar(provider: LocalIndexProvider) -> None:
    response = await provider.search(query(QueryPlace((), (), MEXICO)))

    assert set(slugs([a.url for a in response.articles])) == {"a", "gdl", "penon", "borde"}


async def test_la_enie_se_conserva_y_es_letra(provider: LocalIndexProvider) -> None:
    con_enie = await provider.search(query(None, keywords=("peñón",), exclude=()))
    sin_enie = await provider.search(query(None, keywords=("penon",), exclude=()))

    assert slugs([a.url for a in con_enie.articles]) == ["penon"]
    assert sin_enie.articles == ()


def test_los_caracteres_especiales_se_escapan() -> None:
    assert word_pattern(["C.D.M.X.", "A|B"]) == r"\m(?:C\.D\.M\.X\.|A\|B)\M"
    assert word_pattern([]) is None
