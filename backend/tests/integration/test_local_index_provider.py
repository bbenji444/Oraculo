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
JALISCO = QueryPlace(("Jalisco",), (), MEXICO)
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
    # Caso real del 16/10/2026: GDELT ubicó en Jalisco (14) notas de otros estados.
    note("michoacan", "Hackeo a productores de Uruapan, Michoacán", states=("14",)),
    note("jalisco", "Hackeo al gobierno de Jalisco"),
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


async def test_un_estado_se_busca_por_su_nombre_no_por_la_pista_de_gdelt(
    provider: LocalIndexProvider,
) -> None:
    response = await provider.search(query(JALISCO))

    # La pista de GDELT ya no basta: metía notas de Michoacán (ADR-0014).
    assert slugs([a.url for a in response.articles]) == ["jalisco"]


async def test_mexico_completo_no_filtra_lugar(provider: LocalIndexProvider) -> None:
    response = await provider.search(query(QueryPlace((), (), MEXICO)))

    assert set(slugs([a.url for a in response.articles])) == {
        "a",
        "gdl",
        "penon",
        "borde",
        "michoacan",
        "jalisco",
    }


async def test_la_enie_se_conserva_y_es_letra(provider: LocalIndexProvider) -> None:
    con_enie = await provider.search(query(None, keywords=("peñón",), exclude=()))
    sin_enie = await provider.search(query(None, keywords=("penon",), exclude=()))

    assert slugs([a.url for a in con_enie.articles]) == ["penon"]
    assert sin_enie.articles == ()


async def test_con_subdivision_tambien_debe_aparecer_una_de_sus_palabras(
    provider: LocalIndexProvider,
) -> None:
    # «FGR + tema» (02/11/2026): «hackeo» y además «alcaldía» o «gobierno».
    planned = PlannedQuery(
        Provider.LOCAL_INDEX,
        "t",
        ("hackeo",),
        MEXICO,
        "es",
        WINDOW,
        0,
        ("curso",),
        QueryPlace((), (), MEXICO),
        ("alcaldía", "gobierno"),
    )

    response = await provider.search(planned)

    assert set(slugs([a.url for a in response.articles])) == {"a", "jalisco"}
    assert response.params["subdivision"] == "ALCALDIA | GOBIERNO"


def test_los_caracteres_especiales_se_escapan() -> None:
    assert word_pattern(["C.D.M.X.", "A|B"]) == r"\m(?:C\.D\.M\.X\.|A\|B)\M"
    assert word_pattern([]) is None


def body_note(slug: str, title: str, phrases: list[str]) -> NewsItem:
    return NewsItem.create(
        source="gdelt_ngrams",
        url=f"https://medio.mx/{slug}",
        title=title,
        published_at=NOON,
        body_phrases=phrases,
    )


@pytest.fixture
async def body_provider(sync_engine: Engine, test_engine: AsyncEngine) -> LocalIndexProvider:
    await PostgresNewsIndex(test_engine).add(
        [
            # Palabra clave y lugar solo en el cuerpo: el título no dice nada.
            body_note(
                "cuerpo", "Detienen a un hombre", ["por el hackeo a", "en la alcaldía Iztapalapa"]
            ),
            # "curso" en el cuerpo no la tira: las exclusiones van al título.
            body_note(
                "en_curso", "Investigan robo", ["el hackeo sigue en", "en curso en Iztapalapa"]
            ),
            # Las palabras no se "pegan" entre dos frases distintas.
            body_note("pegadas", "Otra nota", ["termina en hackeo", "Iztapalapa empieza aquí"]),
            body_note("lejos", "Robo", ["hackeo en Monterrey hoy"]),
        ]
    )
    return LocalIndexProvider(test_engine)


async def test_tambien_busca_en_las_frases_del_cuerpo(body_provider: LocalIndexProvider) -> None:
    response = await body_provider.search(query(IZTAPALAPA))

    assert set(slugs([a.url for a in response.articles])) == {"cuerpo", "en_curso", "pegadas"}


async def test_la_subdivision_cuenta_en_el_titulo_no_en_el_cuerpo(
    body_provider: LocalIndexProvider,
) -> None:
    # Benji, 03/11/2026: «título o resumen». La palabra clave puede estar en
    # el cuerpo; la de la subdivisión, no.
    def planned(topic: tuple[str, ...]) -> PlannedQuery:
        return PlannedQuery(
            Provider.LOCAL_INDEX,
            "t",
            ("hackeo",),
            MEXICO,
            "es",
            WINDOW,
            0,
            (),
            QueryPlace((), (), MEXICO),
            topic,
        )

    only_in_body = await body_provider.search(planned(("alcaldía",)))
    in_title = await body_provider.search(planned(("robo",)))

    assert only_in_body.articles == ()
    assert set(slugs([a.url for a in in_title.articles])) == {"en_curso", "lejos"}


async def test_una_frase_de_dos_palabras_no_cruza_frases(body_provider: LocalIndexProvider) -> None:
    response = await body_provider.search(query(None, keywords=("hackeo iztapalapa",), exclude=()))

    assert response.articles == ()
