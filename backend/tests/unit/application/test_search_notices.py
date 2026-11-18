"""Aviso del worker en ``progress.notice`` cuando Google web no pudo buscar (ADR-0115).

Revisión del 18/11/2026: si SearchApi se queda sin saldo a media búsqueda, la
búsqueda sigue con las demás fuentes, no queda «parcial» por eso y el
analista ve «Google web no pudo buscar: sin créditos de SearchApi».
"""

from uuid import uuid4

import pytest

from app.application.audit import Actor
from app.application.ports.search_store import ProcessingErrorRecord, SearchClosing
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionLimits
from app.application.use_cases.extraction import ExtractTexts
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.run_search import PipelineLimits, RunSearch
from app.application.use_cases.search_notices import (
    NOTICE_KEY,
    NoticedSearchStore,
    SearchNotices,
)
from app.domain.budget import QueryCaps
from app.domain.enrichment import LLMUsage
from app.domain.errors import ProviderNoCreditsError
from app.domain.queries import Provider
from app.domain.search import SearchStatus, Stage
from tests.unit import fake_gazetteer as cat
from tests.unit.application.test_execute_queries import FakeCache, FakeLog
from tests.unit.application.test_run_search import (
    DEFAULT_REPLIES,
    IZTA_LOCAL,
    LLM,
    Articles,
    Extractor,
    Searches,
    Source,
    stored_search,
)
from tests.unit.fake_regions import ALL as ALL_REGIONS
from tests.unit.fake_regions import FakeRegionRepository

pytestmark = pytest.mark.anyio

NO_CREDITS = "Google web no pudo buscar: sin créditos de SearchApi"
CLOSING = SearchClosing(SearchStatus.COMPLETED, {"stage": "close"}, 0, LLMUsage(0, 0), 0.0, 3, None)


async def test_sin_aviso_el_avance_pasa_tal_cual() -> None:
    inner = Searches(None)
    store = NoticedSearchStore(inner, SearchNotices())
    search_id = uuid4()

    await store.set_progress(search_id, {"stage": "query"})
    await store.finish(search_id, CLOSING, Actor("benji"))

    assert inner.progress == [{"stage": "query"}]
    assert inner.closing == CLOSING


async def test_con_aviso_va_en_cada_avance_y_al_cerrar() -> None:
    inner = Searches(None)
    notices = SearchNotices()
    store = NoticedSearchStore(inner, notices)
    search_id, other = uuid4(), uuid4()
    notices.put(search_id, NO_CREDITS)

    await store.set_progress(search_id, {"stage": "dedupe"})
    await store.set_progress(other, {"stage": "dedupe"})
    await store.finish(search_id, CLOSING, Actor("benji"))

    assert inner.progress == [
        {"stage": "dedupe", NOTICE_KEY: NO_CREDITS},
        {"stage": "dedupe"},
    ]
    assert inner.closing is not None
    assert inner.closing.progress == {"stage": "close", NOTICE_KEY: NO_CREDITS}
    assert inner.closing.status is SearchStatus.COMPLETED


async def test_lo_demas_pasa_a_la_fila_de_siempre() -> None:
    search = stored_search()
    inner = Searches(search)
    store = NoticedSearchStore(inner, SearchNotices())
    error = ProcessingErrorRecord(search.search_id, Stage.QUERY, "X", "algo")

    assert await store.load(search.search_id) is search
    await store.start(search.search_id)
    await store.record_error(error)

    assert (inner.started, inner.errors) == (True, [error])


async def test_de_punta_a_punta_google_web_sin_saldo_no_vuelve_parcial_la_busqueda() -> None:
    no_credits = ProviderNoCreditsError(
        "SearchApi no tiene créditos (HTTP 429): No searches left",
        provider="searchapi_web",
        http_status=429,
    )
    sources = [
        Source(Provider.SEARCHAPI_WEB, [], cost=1, error=no_credits),
        Source(Provider.LOCAL_INDEX, [IZTA_LOCAL]),
    ]
    providers = {s.provider: s for s in sources}
    search = stored_search()
    inner = Searches(search)
    notices = SearchNotices()
    log = FakeLog()
    use_case = RunSearch(
        searches=NoticedSearchStore(inner, notices),
        articles=Articles(),
        regions=FakeRegionRepository(ALL_REGIONS),
        gazetteer=cat.FakeGazetteer(),
        providers=providers,
        executor=ExecuteQueries(
            providers,
            FakeCache(),
            log,
            ExecutionLimits(QueryCaps(10, 24), 0, {Provider.SEARCHAPI: 100}),
            on_notice=notices.put,
        ),
        extractor=ExtractTexts(Extractor({}), 2),
        llm=LLM(DEFAULT_REPLIES),
        geocoder=GeocodeMentions(cat.FakeGazetteer()),
        similarity=lambda a, b: 1.0 if a == b else 0.0,
        limits=PipelineLimits(150, 2, 0.10, 0.50),
    )

    report = await use_case.run(search.search_id)

    assert report.status is SearchStatus.COMPLETED
    assert report.articles == 1
    assert inner.closing is not None
    assert inner.closing.progress[NOTICE_KEY] == NO_CREDITS
    assert inner.closing.error_summary is None
    # El registro de peticiones sí guarda el error real, para auditar.
    assert sorted((r.provider, r.status, r.http_status) for r in log.records) == [
        ("indice_local", "ok", 200),
        ("searchapi_web", "error", 429),
    ]
