"""Saldo real de SearchApi en los switches, la estimación y la búsqueda rápida (ADR-0115).

Revisión del 18/11/2026 (hallazgos 1 y 9): Google web nunca entraba en la
búsqueda rápida porque la pantalla mandaba las fuentes encendidas por
defecto (las manuales, sin Google web), y «sin créditos» solo se medía con el
tope local de 100 al mes, cuando a la cuenta le quedaban 46 créditos que no se
renuevan. Ahora se lee el saldo real de la cuenta (``GET /api/v1/me``) y, si
no se puede, se usa el tope local.
"""

import pytest

from app.application.use_cases.plan_search import PlanSearch, SearchRequest
from app.application.use_cases.quick_search import QuickSearchRequest, StartQuickSearch
from app.application.use_cases.start_search import StartSearch
from app.application.use_cases.suggest_terms import SuggestConceptTerms
from app.domain.budget import NO_WEB_CREDITS_NOTICE
from app.domain.errors import CreditLimitReachedError
from app.domain.queries import Provider
from tests.unit.application.test_execute_queries import FakeLog
from tests.unit.application.test_plan_search import OPENAI, WEEK, concept
from tests.unit.application.test_quick_search import REGIONS, TEXT
from tests.unit.application.test_run_search import Source
from tests.unit.application.test_start_search import CAPS, Queue, Store
from tests.unit.application.test_suggest_terms import ACTOR, PRICES, FakeSuggester, result
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import IZTAPALAPA, FakeRegionRepository

pytestmark = pytest.mark.anyio

# MANUAL_DEFAULT_SOURCES y QUICK_DEFAULT_SOURCES: Google web solo va por
# defecto en la búsqueda rápida (una consulta por concepto; ADR-0115).
MANUAL = (Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX)
DEFAULTS = (*MANUAL, Provider.SEARCHAPI_WEB)
PAID = (Provider.SEARCHAPI, Provider.SEARCHAPI_WEB)


class FakeBalance:
    """``CreditBalancePort`` en memoria: el saldo que diría SearchApi."""

    def __init__(self, value: int | None) -> None:
        self.value = value
        self.calls = 0

    async def remaining(self) -> int | None:
        self.calls += 1
        return self.value


def planner(
    balance: FakeBalance | None,
    *,
    used: int = 10,
    limit: int = 100,
    repo: FakeConceptRepository | None = None,
) -> PlanSearch:
    return PlanSearch(
        concepts=repo or FakeConceptRepository(),
        regions=FakeRegionRepository(REGIONS),
        providers={
            p: Source(p, [], cost=1 if p in PAID else 0) for p in (Provider.SEARCHAPI, *DEFAULTS)
        },
        log=FakeLog(used=used),
        llm=OPENAI,
        llm_max_articles=150,
        credits_limit=limit,
        default_sources=MANUAL,
        quick_default_sources=DEFAULTS,
        balance=balance,
    )


async def switches(plan: PlanSearch) -> dict[str, tuple[bool, int | None]]:
    """Por fuente: si va encendida en la búsqueda rápida y cuántos créditos quedan."""
    return {
        o.source.provider.value: (o.quick_default_on, o.credits_remaining)
        for o in await plan.source_options()
    }


async def test_con_saldo_google_web_va_encendido_y_dice_cuanto_queda() -> None:
    # Quedan 46 en la cuenta y 90 en el tope local: manda el menor.
    found = await switches(planner(FakeBalance(46)))

    assert found == {
        "google_news_rss": (True, None),
        "indice_local": (True, None),
        "searchapi": (False, 46),
        "searchapi_web": (True, 46),
    }


async def test_en_la_manual_google_web_va_apagado_aunque_haya_saldo() -> None:
    # Una consulta por concepto: la FGR con subdivisiones gastaría varios de
    # los créditos que no se renuevan. En la manual se enciende con su switch.
    options = await planner(FakeBalance(46)).source_options()

    manual = {o.source.provider.value: o.default_on for o in options}

    assert manual == {
        "google_news_rss": True,
        "indice_local": True,
        "searchapi": False,
        "searchapi_web": False,
    }


async def test_sin_fuentes_rapidas_propias_la_rapida_usa_las_de_la_manual() -> None:
    plan = PlanSearch(
        concepts=FakeConceptRepository(),
        regions=FakeRegionRepository(REGIONS),
        providers={p: Source(p, [], cost=0) for p in MANUAL},
        log=FakeLog(),
        llm=OPENAI,
        llm_max_articles=150,
        credits_limit=100,
        default_sources=MANUAL,
    )

    options = await plan.source_options()

    assert all(o.quick_default_on == o.default_on for o in options)


async def test_sin_saldo_en_la_cuenta_google_web_va_apagado() -> None:
    plan = planner(FakeBalance(0))

    found = await switches(plan)

    assert found["searchapi_web"] == (False, 0)
    # Sigue configurado: el analista puede ver por qué está apagado.
    assert all(o.configured for o in await plan.source_options())


async def test_el_tope_local_tambien_manda_aunque_la_cuenta_tenga_saldo() -> None:
    found = await switches(planner(FakeBalance(46), used=100, limit=100))

    assert found["searchapi_web"] == (False, 0)


@pytest.mark.parametrize("balance", [FakeBalance(None), None])
async def test_si_no_se_sabe_el_saldo_se_usa_el_tope_local(balance: FakeBalance | None) -> None:
    assert (await switches(planner(balance)))["searchapi_web"] == (True, 90)
    assert (await switches(planner(balance, used=100)))["searchapi_web"] == (False, 0)


def fgr_request(
    repo: FakeConceptRepository, providers: tuple[Provider, ...] | None = None
) -> SearchRequest:
    fgr = repo.add(concept("FGR"))
    return SearchRequest("benji", (fgr.id,), IZTAPALAPA.id, WEEK, providers)


async def test_la_estimacion_no_cabe_si_la_cuenta_no_tiene_saldo() -> None:
    repo = FakeConceptRepository()
    request = fgr_request(repo, DEFAULTS)

    empty = await planner(FakeBalance(0), repo=repo).estimate(request)
    enough = await planner(FakeBalance(5), repo=repo).estimate(request)

    assert (empty.credits, empty.credits_balance, empty.over_limit) == (1, 0, True)
    assert (enough.credits, enough.credits_balance, enough.over_limit) == (1, 5, False)


async def test_sin_consultas_de_pago_no_se_pregunta_el_saldo() -> None:
    repo = FakeConceptRepository()
    balance = FakeBalance(0)
    request = fgr_request(repo, (Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX))

    estimate = await planner(balance, repo=repo).estimate(request)

    assert (estimate.credits, estimate.credits_balance, estimate.over_limit) == (0, None, False)
    assert balance.calls == 0


async def test_lanzar_con_google_web_sin_saldo_lo_dice_claro() -> None:
    repo = FakeConceptRepository()
    request = fgr_request(repo, (Provider.SEARCHAPI_WEB, Provider.LOCAL_INDEX))
    store, queue = Store(), Queue()
    start = StartSearch(planner(FakeBalance(0), repo=repo), store, queue, CAPS)

    with pytest.raises(CreditLimitReachedError) as caught:
        await start.execute(request)

    assert "no tiene saldo" in caught.value.message
    assert caught.value.details["saldo_de_la_cuenta"] == 0
    assert (store.created, queue.sent) == ([], [])


async def test_la_busqueda_rapida_sin_saldo_real_busca_sin_google_web_y_avisa() -> None:
    # El tope local deja (10 de 100), pero la cuenta ya no tiene saldo.
    repo = FakeConceptRepository()
    store, queue = Store(), Queue()
    suggester = SuggestConceptTerms(FakeSuggester(result("filtran datos")), PRICES, repo)
    regions = FakeRegionRepository(REGIONS)
    start = StartSearch(planner(FakeBalance(0), repo=repo), store, queue, CAPS)
    use = StartQuickSearch(suggester, repo, start, regions)

    # La pantalla manda las de la búsqueda rápida (con Google web).
    started = await use.execute(
        QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK, DEFAULTS), ACTOR
    )

    assert store.created[0].providers == (Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX)
    assert started.notice == NO_WEB_CREDITS_NOTICE
    assert queue.sent == [started.search.search_id]
