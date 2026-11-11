"""Adaptador de Google News RSS con las respuestas reales grabadas el 16/10/2026."""

from datetime import UTC, date, datetime
from pathlib import Path

import httpx2
import pytest

from app.adapters.providers.google_news_rss import (
    RSS_URL,
    GoogleNewsRssProvider,
    edition_params,
    parse_items,
    strip_source_suffix,
)
from app.adapters.providers.http import ProviderHttpClient
from app.domain.errors import ProviderNotConfiguredError, ProviderResponseError
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "providers"
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
WEEK = DateWindow.last_days(7, date(2026, 10, 16))
FIXED = DateWindow.between(date(2026, 10, 8), date(2026, 10, 14))


def fixture(name: str) -> str:
    return (FIXTURES / f"google_news_rss_{name}.xml").read_text(encoding="utf-8")


def query(window: DateWindow = WEEK, country: CountryFilter = MEXICO) -> PlannedQuery:
    return PlannedQuery(
        provider=Provider.GOOGLE_NEWS_RSS,
        text="hackeo CDMX when:7d",
        keywords=("hackeo",),
        country=country,
        language="es",
        window=window,
        estimated_credits=0,
    )


def test_normaliza_las_39_notas_reales() -> None:
    articles, discarded = parse_items(fixture("cdmx_7d"))

    assert (len(articles), discarded) == (39, 0)
    first = articles[0]
    assert first.provider is Provider.GOOGLE_NEWS_RSS
    assert first.provider_rank == 1
    # Sin el " - Milenio" que Google agrega al título.
    assert first.title.startswith("Hackers atacan masivamente a supermercados")
    assert not first.title.endswith("Milenio")
    assert (first.source_name, first.source_domain) == ("Milenio", "milenio.com")
    assert first.published_at == datetime(2026, 10, 12, 20, 3, tzinfo=UTC)
    # El link es de Google: el medio sale de <source> (plan aprobado de F3).
    assert first.url.startswith("https://news.google.com/rss/articles/")
    assert first.raw["guid"]


def test_todas_las_notas_traen_medio_y_fecha() -> None:
    articles, _ = parse_items(fixture("cdmx_7d"))

    assert all(a.source_domain and a.published_at for a in articles)
    assert all(a.provider_rank == i for i, a in enumerate(articles, start=1))


def test_rango_fijo_descarta_lo_que_google_devuelve_fuera_de_fechas() -> None:
    # Pedido: del 8 al 14 de octubre; Google mandó 4 notas del 15 y 16.
    articles, discarded = parse_items(fixture("cdmx_rango_fijo"), FIXED)

    assert (len(articles), discarded) == (34, 4)
    assert all(a.published_at and FIXED.contains(a.published_at, UTC) for a in articles)


def test_xml_roto_es_error_de_respuesta() -> None:
    with pytest.raises(ProviderResponseError, match="XML válido"):
        parse_items("<html>Servicio no disponible")


def test_quita_el_medio_del_titulo_solo_si_coincide() -> None:
    assert strip_source_suffix("Ataque a alcaldía - Milenio", "Milenio") == "Ataque a alcaldía"
    assert strip_source_suffix("Robo - asalto en CDMX", "Milenio") == "Robo - asalto en CDMX"
    assert strip_source_suffix("Sin medio", None) == "Sin medio"


@pytest.mark.parametrize(
    ("country", "expected"),
    [
        (MEXICO, {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}),
        (
            CountryFilter("Colombia", "CO", "CO", "Colombia"),
            {"hl": "es-419", "gl": "CO", "ceid": "CO:es-419"},
        ),
        (
            CountryFilter("Somalilandia", None, None, "Somaliland"),
            {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"},
        ),
    ],
)
def test_edicion_por_pais(country: CountryFilter, expected: dict[str, str]) -> None:
    assert edition_params(country) == expected


@pytest.mark.anyio
async def test_search_envia_la_consulta_y_normaliza() -> None:
    sent: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(200, text=fixture("cdmx_7d"))

    http = ProviderHttpClient(
        Provider.GOOGLE_NEWS_RSS,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(handler),
    )
    provider = GoogleNewsRssProvider(http, enabled=True)

    response = await provider.search(query())

    assert str(sent[0].url).startswith(RSS_URL)
    assert sent[0].url.params["q"] == "hackeo CDMX when:7d"
    assert sent[0].url.params["ceid"] == "MX:es-419"
    # 7 días contando hoy: 4 notas del octavo día quedan fuera (11/11/2026).
    assert (response.http_status, len(response.articles)) == (200, 35)
    assert provider.estimate_cost(query()) == 0
    assert provider.is_configured() is True
    await http.aclose()


@pytest.mark.anyio
async def test_desactivado_no_envia_nada_y_explica_por_que() -> None:
    sent: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(200, text=fixture("cdmx_7d"))

    http = ProviderHttpClient(
        Provider.GOOGLE_NEWS_RSS,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(handler),
    )
    provider = GoogleNewsRssProvider(http, enabled=False)

    assert provider.is_configured() is False
    # Apagado a propósito: dice cómo volver a encenderlo (ADR-0021).
    with pytest.raises(ProviderNotConfiguredError, match="ADR-0021"):
        await provider.search(query())
    assert sent == []
    await http.aclose()
