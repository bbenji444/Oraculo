"""Adaptador de SearchApi con el formato de su documentación (sin red).

Todavía no hay respuesta real grabada (falta la llave). El ejemplo replica
los campos de ``organic_results`` que publica
https://www.searchapi.io/docs/google-news; VERIFICAR con la primera consulta
real aprobada y reemplazarlo por el fixture grabado.
"""

import json
from datetime import UTC, date, datetime

import httpx2
import pytest

from app.adapters.providers.http import ProviderHttpClient
from app.adapters.providers.searchapi import (
    SEARCHAPI_URL,
    SearchApiProvider,
    parse_results,
    time_params,
)
from app.domain.errors import ProviderNotConfiguredError, ProviderResponseError
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider

TODAY = date(2026, 10, 16)
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
DOCUMENTED = {
    "organic_results": [
        {
            "position": 1,
            "title": "Alcaldía sufre ataque de ransomware",
            "link": "https://www.milenio.com/policia/ataque-ransomware",
            "source": "Milenio",
            "date": "hace 19 horas",
            "snippet": "La alcaldía informó que sus sistemas...",
        },
        {"position": 2, "title": "Sin link"},
    ]
}


def query(window: DateWindow, country: CountryFilter = MEXICO) -> PlannedQuery:
    return PlannedQuery(
        provider=Provider.SEARCHAPI,
        text="hackeo Iztapalapa",
        keywords=("hackeo",),
        country=country,
        language="es",
        window=window,
        estimated_credits=1,
    )


@pytest.mark.parametrize(
    ("days", "expected"), [(1, "last_day"), (7, "last_week"), (30, "last_month")]
)
def test_rangos_relativos_conocidos(days: int, expected: str) -> None:
    assert time_params(DateWindow.last_days(days, TODAY)) == {"time_period": expected}


def test_otros_rangos_usan_fechas_en_formato_de_searchapi() -> None:
    assert time_params(DateWindow.last_days(14, TODAY)) == {
        "time_period_min": "10/02/2026",
        "time_period_max": "10/16/2026",
    }


def test_formato_documentado_y_descarta_lo_inutilizable() -> None:
    articles, discarded = parse_results(json.dumps(DOCUMENTED))

    assert discarded == 1
    [article] = articles
    assert (article.provider_rank, article.source_name) == (1, "Milenio")
    assert article.source_domain == "milenio.com"
    # "hace 19 horas" no se convierte hasta ver el formato real (VERIFICAR).
    assert article.published_at is None


def test_usa_iso_date_si_viene() -> None:
    item = {**DOCUMENTED["organic_results"][0], "iso_date": "2026-10-15T14:30:00Z"}

    [article], _ = parse_results(json.dumps({"organic_results": [item]}))

    assert article.published_at == datetime(2026, 10, 15, 14, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("<html>", "no respondió JSON"),
        ('{"error": "Invalid API key."}', "Invalid API key"),
        ('{"organic_results": {}}', "no es una lista"),
    ],
)
def test_respuestas_inesperadas(body: str, fragment: str) -> None:
    with pytest.raises(ProviderResponseError, match=fragment):
        parse_results(body)


def test_sin_resultados_no_es_error() -> None:
    assert parse_results('{"search_metadata": {}}') == ([], 0)


def test_parametros_sin_llave() -> None:
    params = SearchApiProvider(None).request_params(query(DateWindow.last_days(7, TODAY)))

    assert params == {
        "engine": "google_news",
        "q": "hackeo Iztapalapa",
        "gl": "mx",
        "hl": "es",
        "link": "resolved",
        "time_period": "last_week",
    }
    assert not any("key" in name for name in params)


@pytest.mark.anyio
async def test_sin_llave_no_esta_configurado_ni_envia() -> None:
    provider = SearchApiProvider(None)

    assert provider.is_configured() is False
    with pytest.raises(ProviderNotConfiguredError, match="SEARCHAPI_API_KEY"):
        await provider.search(query(DateWindow.last_days(7, TODAY)))


@pytest.mark.anyio
async def test_la_llave_viaja_en_el_encabezado_no_en_la_url() -> None:
    sent: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(200, text=json.dumps(DOCUMENTED))

    http = ProviderHttpClient(
        Provider.SEARCHAPI,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        headers={"Authorization": "Bearer llave-de-prueba"},
        transport=httpx2.MockTransport(handler),
    )
    provider = SearchApiProvider(http)

    response = await provider.search(query(DateWindow.last_days(7, TODAY)))

    assert str(sent[0].url).startswith(SEARCHAPI_URL)
    assert "llave-de-prueba" not in str(sent[0].url)
    assert sent[0].headers["Authorization"] == "Bearer llave-de-prueba"
    assert (
        len(response.articles),
        provider.estimate_cost(query(DateWindow.last_days(7, TODAY))),
    ) == (1, 1)
    await http.aclose()
