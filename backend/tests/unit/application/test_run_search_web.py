"""RunSearch con Google web (ADR-0115): notas sin fecha, redes y el link del medio.

Usa las mismas piezas en memoria que ``test_run_search`` (sin red, base ni
gasto).
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from app.application.ports.search_store import StoredArticle, StoredSearch
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionLimits
from app.application.use_cases.extraction import (
    GOOGLE_LINK_FALLBACK_REASON,
    SOCIAL_FALLBACK_REASON,
    ExtractTexts,
)
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.run_search import PipelineLimits, RunSearch
from app.domain.articles import RawArticle
from app.domain.budget import QueryCaps
from app.domain.dedupe import KnownArticle
from app.domain.enrichment import Enrichment
from app.domain.extraction import ExtractionStatus
from app.domain.names import normalize_name
from app.domain.queries import Provider
from app.domain.schedule import RunWindow
from tests.unit import fake_gazetteer as cat
from tests.unit.application.test_execute_queries import FakeCache, FakeLog
from tests.unit.application.test_run_search import (
    IZTA_MENTION,
    LLM,
    PUBLISHED,
    Articles,
    Extractor,
    Searches,
    Source,
    enrichment,
    stored_search,
)
from tests.unit.fake_regions import ALL as ALL_REGIONS
from tests.unit.fake_regions import FakeRegionRepository

pytestmark = pytest.mark.anyio

POST_URL = "https://www.facebook.com/ivillasenor/posts/1"
POST_TITLE = "Ignacio Gómez Villaseñor"
QUINTA_URL = "https://quintafuerza.mx/mexico/hackean-746-mil-cuentas-de-celular"
FULL = "Hackean 746 mil cuentas de celular, incluidas las de Pillofon"
CUT = "Hackean 746 mil cuentas de celular, incluidas las de"
QUINTA_BODY = (
    f"{FULL}. Un hacker conocido como Eternal ofrece a la venta las cuentas de "
    "clientes de varias telefonías móviles del país. "
) * 4
RSS_TITLE = "Nota sin fecha del RSS"
# Link que Google web no redirigió (contestó su verificación): se queda así.
GOTO_URL = "https://www.google.com/goto?url=CAESHackeanCuentas"
GOTO_TITLE = "Venden 746 mil cuentas de telefonía móvil"
GOOGLE_NEWS = "https://news.google.com/rss/articles/CBMiHackean746"


def web(url: str, title: str, *, source: str | None = None, truncated: bool = False) -> RawArticle:
    return RawArticle.create(
        provider=Provider.SEARCHAPI_WEB,
        provider_rank=1,
        url=url,
        title=title,
        source_name=source,
        snippet="El hacker Eternal ofrece 746 mil cuentas de celular a la venta.",
        published_at=None,
        title_truncated=truncated,
    )


POST = web(POST_URL, POST_TITLE, source="Facebook · Ignacio Gómez Villaseñor")
QUINTA = web(QUINTA_URL, CUT, source="Quinta Fuerza", truncated=True)
RSS_UNDATED = RawArticle.create(
    provider=Provider.GOOGLE_NEWS_RSS,
    provider_rank=1,
    url="https://medio.mx/sin-fecha",
    title=RSS_TITLE,
    published_at=None,
)
REPLIES: dict[str, Enrichment | Exception] = {
    POST_TITLE: enrichment(IZTA_MENTION),
    CUT: enrichment(IZTA_MENTION),
    RSS_TITLE: enrichment(IZTA_MENTION),
    GOTO_TITLE: enrichment(IZTA_MENTION),
}


def pipeline(
    sources: Sequence[Source],
    *,
    search: StoredSearch | None = None,
    articles: Articles | None = None,
    bodies: Mapping[str, str] | None = None,
) -> tuple[RunSearch, Articles, LLM, Extractor]:
    providers = {s.provider: s for s in sources}
    articles = articles or Articles()
    llm = LLM(REPLIES)
    extractor = Extractor(bodies if bodies is not None else {QUINTA_URL: QUINTA_BODY})
    executor = ExecuteQueries(
        providers,
        FakeCache(),
        FakeLog(),
        ExecutionLimits(QueryCaps(10, 24), 0, {Provider.SEARCHAPI: 100}),
    )
    use_case = RunSearch(
        searches=Searches(search or stored_search()),
        articles=articles,
        regions=FakeRegionRepository(ALL_REGIONS),
        gazetteer=cat.FakeGazetteer(),
        providers=providers,
        executor=executor,
        extractor=ExtractTexts(extractor, 2),
        llm=llm,
        geocoder=GeocodeMentions(cat.FakeGazetteer()),
        similarity=lambda a, b: 1.0 if a == b else 0.0,
        limits=PipelineLimits(150, 2, 0.10, 0.50),
    )
    return use_case, articles, llm, extractor


async def test_en_una_busqueda_manual_lo_de_google_web_sin_fecha_se_queda() -> None:
    use_case, articles, llm, _e = pipeline(
        [
            Source(Provider.SEARCHAPI_WEB, [POST, QUINTA], cost=1),
            Source(Provider.GOOGLE_NEWS_RSS, [RSS_UNDATED]),
        ]
    )

    report = await use_case.run(uuid4())

    # Google web ya filtró por fecha; lo del RSS sin fecha sigue fuera.
    assert report.articles == 2
    assert set(articles.ids) == {
        "https://facebook.com/ivillasenor/posts/1",
        QUINTA_URL,
    }
    assert sorted(r.title for r in llm.requests) == sorted([POST_TITLE, CUT])


async def test_en_una_corrida_automatica_lo_sin_fecha_nunca_se_queda() -> None:
    window = RunWindow(PUBLISHED - timedelta(hours=8), PUBLISHED + timedelta(hours=1))
    search = replace(stored_search(), time_window=window)
    use_case, articles, llm, _e = pipeline(
        [Source(Provider.SEARCHAPI_WEB, [POST, QUINTA], cost=1)], search=search
    )

    report = await use_case.run(uuid4())

    assert report.articles == 0
    assert articles.ids == {}
    assert llm.requests == []


async def test_una_publicacion_de_red_no_se_descarga() -> None:
    use_case, articles, llm, extractor = pipeline([Source(Provider.SEARCHAPI_WEB, [POST], cost=1)])

    report = await use_case.run(uuid4())

    assert extractor.urls == []
    [text] = articles.texts.values()
    assert (text.status, text.reason) == (ExtractionStatus.FALLBACK, SOCIAL_FALLBACK_REASON)
    assert text.text.startswith(f"{POST_TITLE}. El hacker Eternal")
    assert report.fallback == 1
    # La IA la lee igual, con título y fragmento.
    assert [r.title for r in llm.requests] == [POST_TITLE]


async def test_un_link_de_google_sin_resolver_no_se_descarga() -> None:
    # Descargarlo daría la página «Verificando tu solicitud» de Google.
    goto = web(GOTO_URL, GOTO_TITLE, source="El Imparcial")
    use_case, articles, llm, extractor = pipeline(
        [Source(Provider.SEARCHAPI_WEB, [goto], cost=1)], bodies={GOTO_URL: QUINTA_BODY}
    )

    report = await use_case.run(uuid4())

    assert extractor.urls == []
    [text] = articles.texts.values()
    assert (text.status, text.reason) == (ExtractionStatus.FALLBACK, GOOGLE_LINK_FALLBACK_REASON)
    assert report.fallback == 1
    # La IA la lee con título y fragmento, y la nota conserva su link de Google.
    assert [r.title for r in llm.requests] == [GOTO_TITLE]
    assert set(articles.ids) == {"https://google.com/goto?url=CAESHackeanCuentas"}


def upgrade_store(extraction_status: str) -> Articles:
    # La nota ya estaba guardada con el link de Google News (RSS), leída solo
    # con título y fragmento: así la IA marcó no relevantes las de «Hacker Eternal».
    known = KnownArticle(7, GOOGLE_NEWS, normalize_name(FULL), PUBLISHED, "quintafuerza.mx")
    return Articles(
        stored_titles=[known],
        by_id={
            7: StoredArticle(
                7, "enrich_v1", frozenset({3}), "09007", extraction_status=extraction_status
            )
        },
    )


async def test_el_link_del_medio_hace_que_se_vuelva_a_leer_la_nota_guardada() -> None:
    articles = upgrade_store(ExtractionStatus.FALLBACK.value)
    use_case, _a, llm, extractor = pipeline(
        [Source(Provider.SEARCHAPI_WEB, [QUINTA], cost=1)], articles=articles
    )

    report = await use_case.run(uuid4())

    # Es la misma nota (el título cortado es el inicio del guardado) y ahora
    # sí hay de dónde leerla: se baja y la IA la vuelve a juzgar.
    assert extractor.urls == [QUINTA_URL]
    assert articles.texts[7].status is ExtractionStatus.OK
    assert [r.title for r in llm.requests] == [CUT]
    assert 7 in articles.enriched
    assert report.reused == 0
    assert 7 in {r.article_id for r in articles.rows}


async def test_si_ya_se_habia_leido_completa_no_se_vuelve_a_pagar() -> None:
    articles = upgrade_store(ExtractionStatus.OK.value)
    use_case, _a, llm, extractor = pipeline(
        [Source(Provider.SEARCHAPI_WEB, [QUINTA], cost=1)], articles=articles
    )

    report = await use_case.run(uuid4())

    assert (extractor.urls, llm.requests, report.reused) == ([], [], 1)
