"""Adaptador de BrowserWork (ADR-0028) con un servidor simulado: sin red ni navegador.

Las respuestas siguen el formato de la API de BrowserWork (``app/main.py`` y
``app/store.py`` de su repositorio, leídos el 24/10/2026). Se reemplazan por
respuestas grabadas de una llamada real en cuanto Benji la autorice.
"""

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx2
import pytest

from app.adapters.providers.browserwork import BrowserWorkProvider, parse_results
from app.adapters.providers.http import ProviderHttpClient
from app.domain.errors import (
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider

pytestmark = pytest.mark.anyio

BASE = "http://browserwork.test:8787"
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
WINDOW = DateWindow.between(date(2026, 10, 23), date(2026, 10, 24))
RESULTS = {
    "id": "job-1",
    "status": "done",
    "results": [
        {
            "title": "Cateo de la FGR en Monterrey deja tres detenidos",
            "url": "https://www.milenio.com/policia/cateo-fgr-monterrey",
            "display_url": "milenio.com › policia",
            "site_name": "Milenio",
            "description": "Elementos de la FGR realizaron un cateo…",
            "engine": "bing",
            "page": 1,
            "rank": 1,
        },
        {"title": "", "url": "https://sin-titulo.mx", "rank": 2},
        {
            "title": "FGR asegura armas en Sinaloa",
            "url": "https://www.infobae.com/mexico/fgr-sinaloa",
            "site_name": "Infobae",
            "description": "",
            "rank": 3,
        },
    ],
}


def query(provider: Provider = Provider.BROWSERWORK_BING) -> PlannedQuery:
    return PlannedQuery(
        provider=provider,
        text='("Fiscalia General de la Republica" OR FGR) -simulacro',
        keywords=("FGR",),
        country=MEXICO,
        language="es",
        window=WINDOW,
        estimated_credits=0,
    )


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def server(
    statuses: list[str], sent: list[httpx2.Request]
) -> Callable[[httpx2.Request], httpx2.Response]:
    """BrowserWork simulado: el trabajo pasa por ``statuses`` y luego da resultados."""
    remaining = list(statuses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/api/search":
            return httpx2.Response(200, json={"id": "job-1", "status": "queued"})
        if request.method == "POST" and path == "/search/job-1/abort":
            return httpx2.Response(200, text="<html>cancelado</html>")
        if path == "/api/search/job-1":
            status = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            return httpx2.Response(200, json={"id": "job-1", "status": status, "error": None})
        if path == "/api/search/job-1/results":
            return httpx2.Response(200, json=RESULTS)
        return httpx2.Response(404, json={"detail": "no existe"})

    return handler


def provider(
    sent: list[httpx2.Request],
    statuses: list[str],
    *,
    base_url: str | None = BASE,
    clock: FakeClock | None = None,
    which: Provider = Provider.BROWSERWORK_BING,
) -> tuple[BrowserWorkProvider, ProviderHttpClient]:
    http = ProviderHttpClient(
        which,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        transport=httpx2.MockTransport(server(statuses, sent)),
    )
    the_clock = clock or FakeClock()

    async def sleep(seconds: float) -> None:
        the_clock.now += seconds

    return (
        BrowserWorkProvider(
            which,
            http,
            base_url=base_url,
            pages=1,
            timeout_seconds=240,
            poll_seconds=3,
            sleep=sleep,
            clock=the_clock,
        ),
        http,
    )


def test_normaliza_los_resultados_sin_fecha() -> None:
    articles, discarded = parse_results(RESULTS, Provider.BROWSERWORK_BING)

    assert discarded == 1  # el resultado sin título
    first = articles[0]
    assert (first.title, first.source_name, first.source_domain) == (
        "Cateo de la FGR en Monterrey deja tres detenidos",
        "Milenio",
        "milenio.com",
    )
    assert first.snippet == "Elementos de la FGR realizaron un cateo…"
    assert first.published_at is None
    assert [a.provider_rank for a in articles] == [1, 3]
    assert articles[1].snippet is None


def test_sin_lista_de_resultados_es_error_de_formato() -> None:
    with pytest.raises(ProviderResponseError):
        parse_results({"status": "done"}, Provider.BROWSERWORK_BING)


async def test_crea_el_trabajo_espera_y_trae_las_notas() -> None:
    sent: list[httpx2.Request] = []
    bw, http = provider(sent, ["queued", "running", "done"])

    response = await bw.search(query())

    created = sent[0]
    assert (created.method, created.url.path) == ("POST", "/api/search")
    assert json.loads(created.content) == {
        "query": '("Fiscalia General de la Republica" OR FGR) -simulacro',
        "pages": 1,
        "engines": ["bing"],
    }
    assert [r.url.path for r in sent[1:]] == [
        "/api/search/job-1",
        "/api/search/job-1",
        "/api/search/job-1",
        "/api/search/job-1/results",
    ]
    assert len(response.articles) == 2
    assert response.params["job_id"] == "job-1"
    assert bw.estimate_cost(query()) == 0
    # Nunca lista las búsquedas de otras personas.
    assert all(r.url.path != "/api/searches" for r in sent)
    await http.aclose()


async def test_google2_usa_su_motor() -> None:
    sent: list[httpx2.Request] = []
    bw, http = provider(sent, ["done"], which=Provider.BROWSERWORK_GOOGLE2)

    await bw.search(query(Provider.BROWSERWORK_GOOGLE2))

    assert json.loads(sent[0].content)["engines"] == ["google2"]
    await http.aclose()


async def test_si_pide_captcha_cancela_y_la_fuente_falla() -> None:
    sent: list[httpx2.Request] = []
    bw, http = provider(sent, ["running", "awaiting_captcha"])

    with pytest.raises(ProviderUnavailableError, match="captcha"):
        await bw.search(query())

    # Libera el único navegador de su servidor en lugar de esperar a una persona.
    assert ("POST", "/search/job-1/abort") in [(r.method, r.url.path) for r in sent]
    await http.aclose()


async def test_si_falla_en_su_servidor_la_fuente_falla() -> None:
    sent: list[httpx2.Request] = []
    bw, http = provider(sent, ["error"])

    with pytest.raises(ProviderUnavailableError, match="falló"):
        await bw.search(query())
    await http.aclose()


async def test_si_no_termina_a_tiempo_la_fuente_falla() -> None:
    sent: list[httpx2.Request] = []
    clock = FakeClock()
    bw, http = provider(sent, ["running"], clock=clock)

    with pytest.raises(ProviderUnavailableError, match="no terminó en 240 s"):
        await bw.search(query())

    # Preguntó cada 3 s hasta el tope (240 s): 81 consultas de estado.
    assert sum(1 for r in sent if r.url.path == "/api/search/job-1") == 81
    await http.aclose()


async def test_sin_direccion_no_esta_configurado() -> None:
    sent: list[httpx2.Request] = []
    bw, http = provider(sent, ["done"], base_url=None)

    assert bw.is_configured() is False
    with pytest.raises(ProviderNotConfiguredError, match="BROWSERWORK_BASE_URL"):
        await bw.search(query())
    assert sent == []
    await http.aclose()


# --- Respuestas reales grabadas el 25/10/2026 (FGR, México, 2 días; ADR-0028) ---

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "providers"


def recorded(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data


def test_bing_real_trae_paginas_institucionales_no_noticias() -> None:
    # Medido: la búsqueda web sin fecha devuelve los sitios oficiales.
    articles, discarded = parse_results(
        recorded("browserwork_bing_fgr_mexico_2d"), Provider.BROWSERWORK_BING
    )

    assert (len(articles), discarded) == (10, 0)
    assert {a.source_domain for a in articles} <= {
        "fiscalia.com",
        "fgr.org.mx",
        "fiscanet.fgr.org.mx",
        "gob.mx",
        "fgjcdmx.gob.mx",
    }


def test_google2_real_trae_links_reconstruidos_por_browserwork() -> None:
    # Medido: BrowserWork arma la URL con el texto que Google muestra arriba
    # del título (engines.py, _prefer_google_url), no con el link real.
    articles, _ = parse_results(
        recorded("browserwork_google2_fgr_mexico_2d"), Provider.BROWSERWORK_GOOGLE2
    )

    assert "https://3reacciones/" in [a.url for a in articles]
    assert "https://hace6horas/" in [a.url for a in articles]
