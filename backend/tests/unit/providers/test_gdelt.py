"""Adaptador de GDELT: respuestas reales grabadas el 16/10/2026 y formato documentado.

Las dos respuestas reales fueron ``{}`` (sin resultados, con GDELT saturado:
ver CHANGELOG). El formato de un artículo se prueba con un ejemplo armado a
partir de los campos que GDELT publica en su página; VERIFICAR con la primera
respuesta real que traiga notas.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx2
import pytest

from app.adapters.providers.gdelt import (
    GDELT_URL,
    GdeltProvider,
    parse_articles,
    time_params,
)
from app.adapters.providers.http import ProviderHttpClient
from app.domain.errors import ProviderResponseError
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "providers"
WEEK = DateWindow.last_days(7, date(2026, 10, 16))
# VERIFICAR: ejemplo con los campos de ArtList (url, title, seendate, domain,
# language, sourcecountry); no viene de una respuesta real.
DOCUMENTED_ITEM = {
    "url": "https://www.eluniversal.com.mx/metropoli/ataque-informatico",
    "url_mobile": "",
    "title": "Alcaldía reporta ataque informático",
    "seendate": "20261015T143000Z",
    "socialimage": "",
    "domain": "eluniversal.com.mx",
    "language": "Spanish",
    "sourcecountry": "Mexico",
}


@pytest.mark.parametrize("name", ["cdmx_7d", "palabra_sola_7d"])
def test_respuestas_reales_vacias(name: str) -> None:
    body = (FIXTURES / f"gdelt_{name}.json").read_text(encoding="utf-8")

    assert body.strip() == "{}"
    assert parse_articles(body) == ([], 0)


def test_cuerpo_vacio_no_es_error() -> None:
    assert parse_articles("") == ([], 0)


def test_formato_documentado_de_un_articulo() -> None:
    body = json.dumps({"articles": [DOCUMENTED_ITEM, {"url": "", "title": "sin url"}]})

    articles, discarded = parse_articles(body)

    assert discarded == 1
    [article] = articles
    assert article.source_domain == "eluniversal.com.mx"
    assert article.published_at == datetime(2026, 10, 15, 14, 30, tzinfo=UTC)
    assert article.language == "Spanish"


def test_texto_plano_con_200_es_error_de_respuesta() -> None:
    with pytest.raises(ProviderResponseError, match="texto en lugar de JSON"):
        parse_articles("Your search contained a keyword that was too short.")


def test_json_sin_articulos_es_error() -> None:
    with pytest.raises(ProviderResponseError, match="sin 'articles'"):
        parse_articles('{"articles": "x"}')


def test_parametros_de_tiempo_relativos_y_fijos_en_utc() -> None:
    assert time_params(WEEK) == {"timespan": "7d"}
    # 8 de octubre 00:00 en CDMX = 06:00 UTC; 14 de octubre 23:59:59 = 15 a las 05:59:59 UTC.
    assert time_params(DateWindow.between(date(2026, 10, 8), date(2026, 10, 14))) == {
        "startdatetime": "20261008060000",
        "enddatetime": "20261015055959",
    }


@pytest.mark.anyio
async def test_search_envia_los_parametros_documentados() -> None:
    sent: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(200, text="{}")

    http = ProviderHttpClient(
        Provider.GDELT,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(handler),
    )
    query = PlannedQuery(
        provider=Provider.GDELT,
        text="hackeo sourcelang:spanish sourcecountry:MX",
        keywords=("hackeo",),
        country=CountryFilter("México", "MX", "MX", "Mexico"),
        language="es",
        window=WEEK,
        estimated_credits=0,
    )
    provider = GdeltProvider(http)

    response = await provider.search(query)

    params = sent[0].url.params
    assert str(sent[0].url).startswith(GDELT_URL)
    assert (params["mode"], params["format"], params["maxrecords"]) == ("ArtList", "json", "250")
    assert (params["sort"], params["timespan"]) == ("DateDesc", "7d")
    assert response.articles == ()
    assert (provider.estimate_cost(query), provider.is_configured()) == (0, True)
    await http.aclose()
