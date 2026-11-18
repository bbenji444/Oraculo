"""Búsqueda rápida con Google web (ADR-0115): sus fuentes y qué pasa sin créditos."""

from collections.abc import Sequence
from dataclasses import replace

import pytest

from app.application.use_cases.plan_search import PlanSearch, SearchRequest
from app.application.use_cases.quick_search import (
    QUICK_DEFAULT_SOURCES,
    QuickSearchRequest,
    StartQuickSearch,
    without_web,
)
from app.application.use_cases.start_search import StartSearch
from app.application.use_cases.suggest_terms import SuggestConceptTerms
from app.domain.budget import NO_WEB_CREDITS_NOTICE
from app.domain.errors import CreditLimitReachedError
from app.domain.queries import Provider
from tests.unit.application.test_execute_queries import FakeLog
from tests.unit.application.test_plan_search import OPENAI, WEEK
from tests.unit.application.test_quick_search import REGIONS, TEXT
from tests.unit.application.test_run_search import Source
from tests.unit.application.test_start_search import CAPS, Queue, Store
from tests.unit.application.test_suggest_terms import ACTOR, PRICES, FakeSuggester, result
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import IZTAPALAPA, FakeRegionRepository

pytestmark = pytest.mark.anyio

FREE = (Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX)


def quick(
    *, used: int = 0, limit: int = 47, configured: Sequence[Provider] = QUICK_DEFAULT_SOURCES
) -> tuple[StartQuickSearch, Store, Queue]:
    repo = FakeConceptRepository()
    regions = FakeRegionRepository(REGIONS)
    planner = PlanSearch(
        concepts=repo,
        regions=regions,
        providers={
            p: Source(p, [], cost=1 if p in (Provider.SEARCHAPI, Provider.SEARCHAPI_WEB) else 0)
            for p in (Provider.SEARCHAPI, *configured)
        },
        log=FakeLog(used=used),
        llm=OPENAI,
        llm_max_articles=150,
        credits_limit=limit,
        # Las de la búsqueda manual: la rápida trae las suyas.
        default_sources=FREE,
    )
    store, queue = Store(), Queue()
    suggester = SuggestConceptTerms(FakeSuggester(result("filtran datos")), PRICES, repo)
    use = StartQuickSearch(suggester, repo, StartSearch(planner, store, queue, CAPS), regions)
    return use, store, queue


def request(providers: tuple[Provider, ...] | None = None) -> QuickSearchRequest:
    return QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK, providers)


async def test_sin_elegir_fuentes_busca_tambien_en_google_web() -> None:
    use, store, _ = quick()

    started = await use.execute(request(), ACTOR)

    [created] = store.created
    assert created.providers == (Provider.SEARCHAPI_WEB, *FREE)
    # Google web manda una sola consulta (el literal y el municipio), de 1 crédito.
    web = [q for q in started.search.estimate.queries if q.provider is Provider.SEARCHAPI_WEB]
    assert [q.text for q in web] == [f"{TEXT} Iztapalapa"]
    assert started.search.estimate.credits == 1
    assert started.notice is None


async def test_sin_creditos_se_busca_sin_google_web_y_lo_avisa() -> None:
    # La cuenta llegó a su tope: la búsqueda rápida no falla.
    use, store, queue = quick(used=47, limit=47)

    started = await use.execute(request(), ACTOR)

    [created] = store.created
    assert created.providers == FREE
    assert (
        started.notice
        == NO_WEB_CREDITS_NOTICE
        == "Sin créditos de Google web: se buscó en noticias"
    )
    assert started.search.estimate.credits == 0
    assert queue.sent == [started.search.search_id]


async def test_si_el_analista_encendio_google_web_tambien_se_quita_sin_creditos() -> None:
    use, store, _ = quick(used=47, limit=47)

    started = await use.execute(request((Provider.SEARCHAPI_WEB, Provider.LOCAL_INDEX)), ACTOR)

    assert store.created[0].providers == (Provider.LOCAL_INDEX,)
    assert started.notice == NO_WEB_CREDITS_NOTICE


async def test_si_ni_sin_google_web_cabe_el_error_llega_igual() -> None:
    # Encendió también Google News de pago: sin Google web sigue sin caber.
    use, store, queue = quick(used=47, limit=47)

    with pytest.raises(CreditLimitReachedError):
        await use.execute(request((Provider.SEARCHAPI, Provider.SEARCHAPI_WEB)), ACTOR)

    assert (store.created, queue.sent) == ([], [])


async def test_si_google_web_era_la_unica_fuente_el_error_llega_igual() -> None:
    use, store, _ = quick(used=47, limit=47)

    with pytest.raises(CreditLimitReachedError):
        await use.execute(request((Provider.SEARCHAPI_WEB,)), ACTOR)

    assert store.created == []


async def test_sin_llave_de_searchapi_busca_en_noticias_sin_aviso() -> None:
    # Sin llave, Google web no está configurado y se queda fuera solo.
    use, store, _ = quick(configured=FREE)

    started = await use.execute(request(), ACTOR)

    assert store.created[0].providers == FREE
    assert started.notice is None


def test_quitar_google_web_de_una_busqueda() -> None:
    base = SearchRequest("benji", (1,), IZTAPALAPA.id, WEEK, default_sources=QUICK_DEFAULT_SOURCES)

    assert without_web(base) == replace(base, default_sources=FREE)
    chosen = replace(base, providers=(Provider.SEARCHAPI_WEB, Provider.LOCAL_INDEX))
    assert without_web(chosen) == replace(chosen, providers=(Provider.LOCAL_INDEX,))
    assert without_web(replace(base, default_sources=FREE)) is None
    assert without_web(replace(base, providers=(Provider.SEARCHAPI_WEB,))) is None
    assert without_web(replace(base, default_sources=None)) is None
