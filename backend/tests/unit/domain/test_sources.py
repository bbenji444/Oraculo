"""Catálogo de fuentes de la búsqueda manual (F12.2, ADR-0027)."""

import pytest

from app.domain.errors import InvalidRequestError
from app.domain.queries import Provider
from app.domain.sources import SOURCES, parse_sources, resolve_sources, source_of

ALL = (Provider.SEARCHAPI, Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX)


def test_catalogo_ordenado_y_sin_gdelt() -> None:
    assert [s.provider for s in SOURCES] == [
        Provider.GOOGLE_NEWS_RSS,
        Provider.LOCAL_INDEX,
        Provider.SEARCHAPI,
    ]
    assert [s.provider for s in SOURCES if s.paid] == [Provider.SEARCHAPI]
    assert source_of(Provider.GDELT) is None


def test_lo_elegido_manda_en_el_orden_de_siempre() -> None:
    chosen = resolve_sources((Provider.LOCAL_INDEX, Provider.SEARCHAPI), (), ALL)

    assert chosen == (Provider.SEARCHAPI, Provider.LOCAL_INDEX)


def test_sin_elegir_se_usan_las_de_por_defecto_que_esten_configuradas() -> None:
    defaults = (Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX, Provider.SEARCHAPI)

    chosen = resolve_sources(None, defaults, (Provider.LOCAL_INDEX, Provider.SEARCHAPI))

    assert chosen == (Provider.SEARCHAPI, Provider.LOCAL_INDEX)


@pytest.mark.parametrize(
    ("requested", "configured", "message"),
    [
        ((), ALL, "Elige al menos una fuente"),
        (None, (Provider.SEARCHAPI,), "Elige al menos una fuente"),
        (
            (Provider.GOOGLE_NEWS_RSS,),
            (Provider.LOCAL_INDEX,),
            "Google News RSS: no está configurada",
        ),
        ((Provider.GDELT,), (*ALL, Provider.GDELT), "no se puede elegir"),
    ],
)
def test_elecciones_invalidas(
    requested: tuple[Provider, ...] | None, configured: tuple[Provider, ...], message: str
) -> None:
    with pytest.raises(InvalidRequestError, match=message):
        resolve_sources(requested, (Provider.LOCAL_INDEX,), configured)


def test_lee_la_lista_de_por_defecto() -> None:
    assert parse_sources(" indice_local , google_news_rss,indice_local") == (
        Provider.GOOGLE_NEWS_RSS,
        Provider.LOCAL_INDEX,
    )
    assert parse_sources("") == ()


@pytest.mark.parametrize("text", ["bing", "gdelt"])
def test_lista_de_por_defecto_invalida(text: str) -> None:
    with pytest.raises(ValueError):
        parse_sources(text)
