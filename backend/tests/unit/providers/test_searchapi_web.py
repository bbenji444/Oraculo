"""Adaptador de Google web (SearchApi, motor ``google``, ADR-0115), sin red.

La respuesta es la real del 18/11/2026 (``searchapi_web_hacker_eternal_7d``,
1 crédito): 9 resultados orgánicos y 4 videos. Los links ``google.com/goto``
los responde un ``MockTransport`` con un 302 y su ``Location``, como lo hace
Google; los destinos son de prueba.
"""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from app.adapters.providers.factory import build_provider, build_searchapi_web
from app.adapters.providers.http import ProviderHttpClient
from app.adapters.providers.searchapi import SEARCHAPI_URL
from app.adapters.providers.searchapi_web import (
    SearchApiWebProvider,
    parse_page,
    untruncated,
)
from app.core.config import Settings
from app.domain.errors import (
    ProviderAuthError,
    ProviderNoCreditsError,
    ProviderNotConfiguredError,
    ProviderResponseError,
)
from app.domain.platforms import Platform, platform_of
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "providers"
BODY = (FIXTURES / "searchapi_web_hacker_eternal_7d.json").read_text(encoding="utf-8")
TODAY = date(2026, 11, 18)
# La hora en que se grabó la respuesta: «hace 15 horas» se cuenta desde aquí.
NOW = datetime(2026, 11, 18, 19, 3, tzinfo=UTC)
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
GOOGLE_HOST = "www.google.com"
# Lo que contestó Google el 18/11/2026 a links goto pedidos seguidos (resumido).
VERIFICATION_PAGE = (
    "<html><head><title>Google</title></head><body>Verificando tu solicitud. "
    "Podrás continuar en unos segundos. No actualices esta página.</body></html>"
)
# Destino de cada link google.com/goto de los orgánicos 3 a 8, en orden. El
# 9 no se resuelve (Google responde 200 con su verificación) y se queda con
# su link de Google.
DESTINATIONS = (
    "https://www.youtube.com/shorts/Qx1Eternal",
    "https://www.instagram.com/p/DQeternal/",
    "https://quintafuerza.mx/mexico/hackean-746-mil-cuentas-de-celular/",
    "https://m.facebook.com/ivillasenor/posts/pfbid01",
    "https://www.facebook.com/ivillasenor/posts/pfbid02",
    "https://www.elimparcial.com/mexico/hackeo-buro-laboral/",
)


def goto_tokens() -> list[str]:
    links = [r["link"] for r in json.loads(BODY)["organic_results"]]
    return [
        httpx2.URL(link).params["url"] for link in links if httpx2.URL(link).host == GOOGLE_HOST
    ]


def query(window: DateWindow | None = None, country: CountryFilter = MEXICO) -> PlannedQuery:
    return PlannedQuery(
        provider=Provider.SEARCHAPI_WEB,
        text="hacker eternal",
        keywords=("hacker eternal",),
        country=country,
        language="es",
        window=window or DateWindow.last_days(7, TODAY),
        estimated_credits=1,
    )


class Recorder:
    """Responde a SearchApi con la respuesta grabada y a Google con sus 302."""

    def __init__(self, searchapi: httpx2.Response | None = None) -> None:
        self.searchapi_requests: list[httpx2.Request] = []
        self.google_requests: list[httpx2.Request] = []
        self._searchapi = searchapi
        self.targets = dict(zip(goto_tokens(), DESTINATIONS, strict=False))

    def searchapi(self, request: httpx2.Request) -> httpx2.Response:
        self.searchapi_requests.append(request)
        return self._searchapi or httpx2.Response(200, text=BODY)

    def google(self, request: httpx2.Request) -> httpx2.Response:
        self.google_requests.append(request)
        target = self.targets.get(request.url.params.get("url", ""))
        if target is None:
            return httpx2.Response(200, text=VERIFICATION_PAGE)
        return httpx2.Response(302, headers={"Location": target})

    def provider(self, max_pages: int = 1) -> SearchApiWebProvider:
        http = ProviderHttpClient(
            Provider.SEARCHAPI_WEB,
            timeout_seconds=5,
            max_attempts=1,
            max_concurrency=1,
            headers={"Authorization": "Bearer llave-de-prueba"},
            transport=httpx2.MockTransport(self.searchapi),
        )
        resolver = ProviderHttpClient(
            "google_goto",
            timeout_seconds=5,
            max_attempts=1,
            max_concurrency=4,
            transport=httpx2.MockTransport(self.google),
            follow_redirects=False,
        )
        return SearchApiWebProvider(http, resolver, max_pages, now=lambda: NOW)


# --- Lectura de la respuesta real ---


def test_lee_los_9_organicos_y_los_4_videos_de_la_respuesta_real() -> None:
    page = parse_page(BODY)

    assert [h.section for h in page.hits] == ["organic_results"] * 9 + ["inline_videos"] * 4
    assert page.discarded == 0
    # Google ofrece otra página; con SEARCHAPI_WEB_MAX_PAGES=1 no se pide.
    assert page.has_next is True
    assert [h.source_name for h in page.hits[:4]] == [
        "Facebook",
        "X · ivillasenor",
        "YouTube · La Saga - US",
        "Instagram · ivillasenor87",
    ]
    assert page.hits[9].source_name == "YouTube · La Saga"
    assert page.hits[4].date_text == "hace 15 horas"
    # Las imágenes en base64 no se guardan.
    assert all("favicon" not in h.raw and "thumbnail" not in h.raw for h in page.hits)
    assert page.hits[0].raw["section"] == "organic_results"


async def test_resuelve_los_links_de_google_y_conserva_el_que_google_no_redirige() -> None:
    recorder = Recorder()
    provider = recorder.provider()

    response = await provider.search(query())

    articles = response.articles
    # 9 orgánicos + 4 videos: el goto que Google no redirigió ya no se pierde
    # (18/11/2026: así se perdían 8 de 10 resultados reales).
    assert (len(articles), response.discarded) == (13, 0)
    assert [a.provider_rank for a in articles] == list(range(1, 14))
    urls = [a.url for a in articles]
    assert urls[2:8] == list(DESTINATIONS)
    assert urls[8].startswith(f"https://{GOOGLE_HOST}/goto?url=")
    assert articles[8].source_name == "X · ivillasenor"
    assert urls[9] == "https://www.youtube.com/watch?v=jMs7fCiEHRo"
    assert sum(GOOGLE_HOST in u for u in urls) == 1
    # Los 7 goto se piden a Google sin seguirlos y sin la llave de SearchApi.
    assert len(recorder.google_requests) == 7
    assert all("authorization" not in r.headers for r in recorder.google_requests)
    assert (len(recorder.searchapi_requests), response.credits_used, response.pages) == (1, 1, 1)


async def test_fechas_titulos_cortados_y_dominios_de_la_respuesta_real() -> None:
    articles = (await Recorder().provider().search(query())).articles
    by_url = {a.url: a for a in articles}

    facebook = articles[0]
    assert facebook.title == "HACKEO MASIVO: ETERNAL expone 746 MIL cuentas de"
    assert facebook.title_truncated is True
    assert facebook.source_domain == "facebook.com"
    assert facebook.published_at is None
    quinta = by_url[DESTINATIONS[2]]
    assert quinta.source_domain == "quintafuerza.mx"
    assert quinta.published_at == NOW - timedelta(hours=15)
    assert by_url[DESTINATIONS[5]].published_at == NOW - timedelta(days=5)
    tweet = articles[1]
    assert (tweet.title, tweet.title_truncated) == ("Ignacio Gómez Villaseñor", False)


async def test_plataforma_de_cada_resultado_real() -> None:
    articles = (await Recorder().provider().search(query())).articles

    platforms = [
        platform_of(a.source_domain, a.url, (Provider.SEARCHAPI_WEB.value,), a.source_name)
        for a in articles
    ]

    assert platforms == [
        Platform.FACEBOOK,
        Platform.X,
        Platform.YOUTUBE,
        Platform.INSTAGRAM,
        Platform.WEB,  # Quinta Fuerza
        Platform.FACEBOOK,  # m.facebook.com
        Platform.FACEBOOK,
        Platform.WEB,  # El Imparcial: solo lo trajo Google web
        Platform.X,  # link de Google sin resolver: la red sale de «X · ivillasenor»
        *[Platform.YOUTUBE] * 4,
    ]


# --- Parámetros y costo ---


def test_parametros_con_pais_sin_autocorreccion_y_con_periodo() -> None:
    params = SearchApiWebProvider(None).request_params(query())

    assert params == {
        "engine": "google",
        "q": "hacker eternal",
        "gl": "mx",
        "hl": "es",
        "nfpr": "1",
        "time_period": "last_week",
    }
    # Ni verbatim, ni num, ni link (decisión del ADR-0115).
    assert not {"verbatim", "num", "link"} & params.keys()
    assert not any("key" in name for name in params)


def test_en_el_mundo_busca_como_desde_mexico() -> None:
    # Medido el 18/11/2026: «Hacker Eternal» sin ``gl`` (SearchApi busca como
    # desde Estados Unidos) trajo 2 resultados; con gl=mx, 9 páginas y 4
    # videos. En Google web ``gl`` es el país de quien busca, no un filtro.
    params = SearchApiWebProvider(None).request_params(query(country=CountryFilter.world("Mundo")))

    assert (params["gl"], params["hl"], params["nfpr"]) == ("mx", "es", "1")


def test_rango_fijo_usa_fechas_de_searchapi() -> None:
    window = DateWindow.between(date(2026, 11, 1), date(2026, 11, 14))

    params = SearchApiWebProvider(None).request_params(query(window))

    assert (params["time_period_min"], params["time_period_max"]) == ("11/01/2026", "11/14/2026")


def test_cuesta_un_credito_por_pagina() -> None:
    assert SearchApiWebProvider(None).estimate_cost(query()) == 1
    assert SearchApiWebProvider(None, max_pages=2).estimate_cost(query()) == 2


async def test_sin_llave_no_esta_configurado_ni_envia() -> None:
    provider = SearchApiWebProvider(None)

    assert provider.is_configured() is False
    with pytest.raises(ProviderNotConfiguredError, match="SEARCHAPI_API_KEY"):
        await provider.search(query())


def test_la_fabrica_lo_arma_con_la_llave_de_searchapi() -> None:
    def settings(key: SecretStr | None) -> Settings:
        return Settings.model_construct(searchapi_api_key=key)

    assert build_provider(Provider.SEARCHAPI_WEB, settings(SecretStr("llave"))).is_configured()
    assert not build_provider(Provider.SEARCHAPI_WEB, settings(None)).is_configured()


async def test_la_llave_viaja_en_el_encabezado() -> None:
    recorder = Recorder()

    await recorder.provider().search(query())

    [sent] = recorder.searchapi_requests
    assert str(sent.url).startswith(SEARCHAPI_URL)
    assert "llave-de-prueba" not in str(sent.url)
    assert sent.headers["Authorization"] == "Bearer llave-de-prueba"
    assert sent.url.params["engine"] == "google"


# --- Sin créditos y errores ---


# Cambió el requisito (revisión del 18/11/2026): el aviso para el analista lo
# arma ExecuteQueries; el adaptador solo dice de qué tipo es el error, para que
# la búsqueda siga con las demás fuentes sin reintentar.
@pytest.mark.parametrize("status", [402, 429])
async def test_sin_creditos_es_un_error_de_saldo(status: int) -> None:
    recorder = Recorder(httpx2.Response(status, text='{"error": "No credits left"}'))

    with pytest.raises(ProviderNoCreditsError) as caught:
        await recorder.provider().search(query())

    assert caught.value.message.startswith("SearchApi no tiene créditos")
    assert "No credits left" in caught.value.message
    assert caught.value.http_status == status
    assert caught.value.provider == Provider.SEARCHAPI_WEB.value


@pytest.mark.parametrize("status", [401, 403])
async def test_llave_rechazada_es_un_error_de_la_cuenta(status: int) -> None:
    recorder = Recorder(httpx2.Response(status, text='{"error": "Invalid API key."}'))

    with pytest.raises(ProviderAuthError) as caught:
        await recorder.provider().search(query())

    assert caught.value.http_status == status


async def test_otro_error_conserva_su_mensaje() -> None:
    recorder = Recorder(httpx2.Response(400, text='{"error": "Bad q"}'))

    with pytest.raises(ProviderResponseError) as caught:
        await recorder.provider().search(query())

    assert not isinstance(caught.value, ProviderNoCreditsError)
    assert "Bad q" in caught.value.message


async def test_sin_resultados_de_google_no_es_un_error() -> None:
    # Búsqueda real del 18/11/2026 («Pillofon Luisito Comunica», última
    # semana): SearchApi contestó así y la búsqueda quedaba «parcial».
    body = '{"error": "Google didn\'t return any results."}'
    recorder = Recorder(httpx2.Response(200, text=body))

    response = await recorder.provider().search(query())

    assert (len(response.articles), response.discarded) == (0, 0)
    assert recorder.google_requests == []


async def test_la_fabrica_no_reintenta_un_429_de_searchapi() -> None:
    # «Sin reintentos largos»: sin saldo, reintentar solo hace esperar.
    calls: list[httpx2.Request] = []

    def no_credits(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(429, text='{"error": "No credits left"}')

    settings = Settings.model_construct(
        searchapi_api_key=SecretStr("llave"),
        searchapi_timeout_seconds=5,
        provider_max_attempts=3,
        provider_max_concurrency=1,
        searchapi_web_max_pages=1,
    )
    provider = build_searchapi_web(settings, transport=httpx2.MockTransport(no_credits))

    with pytest.raises(ProviderNoCreditsError):
        await provider.search(query())
    assert len(calls) == 1


async def test_sin_resolvedor_los_links_de_google_se_quedan_como_vinieron() -> None:
    recorder = Recorder()
    http = ProviderHttpClient(
        Provider.SEARCHAPI_WEB,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(recorder.searchapi),
    )

    response = await SearchApiWebProvider(http, None, now=lambda: NOW).search(query())

    # Los 7 goto se quedan con su link de Google: abren en el navegador.
    assert (len(response.articles), response.discarded) == (13, 0)
    assert sum(GOOGLE_HOST in a.url for a in response.articles) == 7


async def test_si_google_pide_verificar_ya_no_se_le_preguntan_los_demas_links() -> None:
    # No se intenta pasar su verificación ni se insiste con los demás.
    recorder = Recorder()
    first = next(iter(recorder.targets))
    del recorder.targets[first]

    response = await recorder.provider().search(query())

    assert len(recorder.google_requests) == 1
    assert (len(response.articles), response.discarded) == (13, 0)
    assert sum(GOOGLE_HOST in a.url for a in response.articles) == 7


async def test_si_google_falla_el_link_se_queda_sin_tumbar_la_busqueda() -> None:
    def broken(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503)

    resolver = ProviderHttpClient(
        "google_goto",
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(broken),
        follow_redirects=False,
    )
    provider = SearchApiWebProvider(None, resolver)

    link = "https://www.google.com/goto?url=abc"
    assert await provider.resolve(link) == link


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("https://www.google.com/url?q=https://medio.mx/nota&sa=U", "https://medio.mx/nota"),
        ("https://www.google.com/search?q=x", None),
        ("https://medio.mx/nota", "https://medio.mx/nota"),
        ("ftp://medio.mx/nota", None),
    ],
)
async def test_links_que_no_piden_a_google(link: str, expected: str | None) -> None:
    assert await SearchApiWebProvider(None).resolve(link) == expected


async def test_una_redireccion_de_vuelta_a_google_deja_el_link_como_vino() -> None:
    def consent(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"Location": "https://consent.google.com/ml?x=1"})

    resolver = ProviderHttpClient(
        "google_goto",
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(consent),
        follow_redirects=False,
    )

    resolved = await SearchApiWebProvider(None, resolver).resolve(
        "https://www.google.com/goto?url=abc"
    )

    assert resolved == "https://www.google.com/goto?url=abc"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "Hackean 746 mil cuentas de celular, incluidas las de ...",
            ("Hackean 746 mil cuentas de celular, incluidas las de", True),
        ),
        ("El hacker que …", ("El hacker que", True)),
        ("Título completo", ("Título completo", False)),
        (None, (None, False)),
    ],
)
def test_quita_los_puntos_de_un_titulo_cortado(
    title: str | None, expected: tuple[str | None, bool]
) -> None:
    assert untruncated(title) == expected


def test_lee_tweets_y_noticias_destacadas() -> None:
    body = json.dumps(
        {
            "inline_tweets": [
                {
                    "link": "https://x.com/ivillasenor/status/1",
                    "snippet": "El hacker Eternal ofrece 746 mil cuentas",
                    "author": {"name": "Ignacio Gómez", "screen_name": "ivillasenor"},
                    "date": "hace 2 horas",
                }
            ],
            "top_stories": [
                {"link": "https://www.milenio.com/nota", "title": "Hackeo", "source": "Milenio"}
            ],
            "ads": [{"link": "https://anuncio.mx"}],
            "knowledge_graph": {"title": "Eternal"},
        }
    )

    tweet, story = parse_page(body).hits

    assert (tweet.title, tweet.source_name) == (
        "Ignacio Gómez (@ivillasenor) en X",
        "X · ivillasenor",
    )
    # Hallazgo 8: el medio se guarda limpio; la sección queda en raw.
    assert story.source_name == "Milenio"
    assert story.raw["section"] == "top_stories"


@pytest.mark.parametrize(
    ("body", "fragment"),
    [("<html>", "no respondió JSON"), ('{"error": "Invalid API key."}', "Invalid API key")],
)
def test_respuestas_inesperadas(body: str, fragment: str) -> None:
    with pytest.raises(ProviderResponseError, match=fragment):
        parse_page(body)


# --- Revisión del 18/11/2026: redirecciones raras (hallazgo 6) ---


def resolver_answering(
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> SearchApiWebProvider:
    resolver = ProviderHttpClient(
        "google_goto",
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(handler),
        follow_redirects=False,
    )
    return SearchApiWebProvider(None, resolver)


GOTO = "https://www.google.com/goto?url=abc"


async def test_una_redireccion_mal_formada_deja_el_link_sin_tumbar_nada() -> None:
    def malformed(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"Location": "https://[malformado/x"})

    assert await resolver_answering(malformed).resolve(GOTO) == GOTO


async def test_una_redireccion_a_google_url_q_lleva_al_destino() -> None:
    def via_url(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            302, headers={"Location": "https://www.google.com/url?q=https://quintafuerza.mx/nota"}
        )

    assert await resolver_answering(via_url).resolve(GOTO) == "https://quintafuerza.mx/nota"


async def test_un_error_de_httpx_al_resolver_deja_el_link() -> None:
    def broken(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.DecodingError("respuesta comprimida rota", request=request)

    assert await resolver_answering(broken).resolve(GOTO) == GOTO


async def test_un_link_original_mal_formado_se_descarta() -> None:
    assert await SearchApiWebProvider(None).resolve("https://[malformado/x") is None


async def test_la_busqueda_sigue_aunque_una_redireccion_venga_mal_formada() -> None:
    recorder = Recorder()
    targets = recorder.targets
    first = next(iter(targets))
    targets[first] = "https://[malformado/x"

    response = await recorder.provider().search(query())

    # El mal formado y el que no redirige se quedan con su link de Google; los
    # demás llegan con su destino. Tras el mal formado ya no se pregunta más.
    assert (len(response.articles), response.discarded) == (13, 0)
    assert response.articles[2].url.startswith(f"https://{GOOGLE_HOST}/goto?url=")
