"""Adaptador de SearchApi con el formato de su documentación (sin red).

Todavía no hay respuesta real grabada (falta la llave). El ejemplo replica
los campos de ``organic_results`` que publica
https://www.searchapi.io/docs/google-news; VERIFICAR con la primera consulta
real aprobada y reemplazarlo por el fixture grabado.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

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
    # La página vino con menos de 10 resultados: no se pide otra.
    assert (len(sent), len(response.articles), response.credits_used) == (1, 1, 1)
    # La estimación es el máximo: 3 páginas llenas.
    assert provider.estimate_cost(query(DateWindow.last_days(7, TODAY))) == 3
    await http.aclose()


def test_respuesta_real_de_searchapi() -> None:
    # Primera consulta real (16/10/2026, 1 crédito aprobado por Benji):
    # Ciberseguridad · Ciudad de México · últimos 7 días.
    body = (
        Path(__file__).resolve().parents[2] / "fixtures" / "providers" / "searchapi_cdmx_7d.json"
    ).read_text(encoding="utf-8")

    articles, discarded = parse_results(body)

    assert (len(articles), discarded) == (10, 0)
    first = articles[0]
    assert first.provider_rank == 1
    assert first.source_name == "MILENIO"
    # link=resolved: el link es del medio, no una redirección de Google.
    assert first.source_domain == "milenio.com"
    assert first.published_at == datetime(2026, 10, 12, 20, 3, tzinfo=UTC)
    assert all(a.published_at is not None for a in articles)


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "providers"


def real_page(number: int) -> str:
    # Homicidio · Miguel Hidalgo, 13–20/10/2026: 3 páginas reales (21/10/2026,
    # 3 créditos aprobados por Benji; la cuenta pasó de 94 a 91 restantes).
    return (FIXTURES / f"searchapi_homicidio_pagina_{number}.json").read_text(encoding="utf-8")


def paged_client(pages: dict[int, httpx2.Response]) -> tuple[ProviderHttpClient, list[str]]:
    asked: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        page = int(request.url.params.get("page", "1"))
        asked.append(str(page))
        return pages[page]

    http = ProviderHttpClient(
        Provider.SEARCHAPI,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(handler),
    )
    return http, asked


@pytest.mark.anyio
async def test_tres_paginas_reales_traen_30_notas_distintas_y_cuestan_3() -> None:
    http, asked = paged_client({n: httpx2.Response(200, text=real_page(n)) for n in (1, 2, 3)})

    response = await SearchApiProvider(http, max_pages=3).search(
        query(DateWindow.last_days(7, TODAY))
    )

    assert asked == ["1", "2", "3"]
    assert (len(response.articles), response.credits_used, response.pages) == (30, 3, 3)
    assert [a.provider_rank for a in response.articles] == list(range(1, 31))
    assert len({a.url for a in response.articles}) == 30
    assert response.params["pages"] == "3"
    await http.aclose()


@pytest.mark.anyio
async def test_si_una_pagina_viene_incompleta_no_pide_la_siguiente() -> None:
    short = json.loads(real_page(2))
    short["organic_results"] = short["organic_results"][:4]
    http, asked = paged_client(
        {
            1: httpx2.Response(200, text=real_page(1)),
            2: httpx2.Response(200, text=json.dumps(short)),
        }
    )

    response = await SearchApiProvider(http, max_pages=3).search(
        query(DateWindow.last_days(7, TODAY))
    )

    assert asked == ["1", "2"]
    assert (len(response.articles), response.credits_used) == (14, 2)
    await http.aclose()


@pytest.mark.anyio
async def test_una_pagina_extra_que_falla_conserva_las_anteriores_y_no_se_cobra() -> None:
    http, asked = paged_client(
        {1: httpx2.Response(200, text=real_page(1)), 2: httpx2.Response(500, text="error")}
    )

    response = await SearchApiProvider(http, max_pages=3).search(
        query(DateWindow.last_days(7, TODAY))
    )

    assert asked == ["1", "2"]
    assert (len(response.articles), response.credits_used) == (10, 1)
    await http.aclose()


@pytest.mark.anyio
async def test_una_sola_pagina_si_asi_se_configura() -> None:
    http, asked = paged_client({1: httpx2.Response(200, text=real_page(1))})
    provider = SearchApiProvider(http, max_pages=1)

    response = await provider.search(query(DateWindow.last_days(7, TODAY)))

    assert (asked, response.credits_used) == (["1"], 1)
    assert provider.estimate_cost(query(DateWindow.last_days(7, TODAY))) == 1
    await http.aclose()
