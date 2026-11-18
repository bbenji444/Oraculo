"""Google News y Google web gastan la misma cuenta de SearchApi (ADR-0115)."""

from uuid import UUID, uuid4

import pytest

from app.application.use_cases.execute_queries import ExecutionStatus
from app.application.use_cases.plan_search import PlanSearch, SearchRequest
from app.domain.budget import (
    account_label,
    account_providers,
    credit_account,
)
from app.domain.errors import ProviderAuthError, ProviderNoCreditsError, ProviderResponseError
from app.domain.queries import Provider
from tests.unit.application.test_execute_queries import FakeLog, FakeProvider, planned, use_case
from tests.unit.application.test_plan_search import NOW, OPENAI, WEEK, concept
from tests.unit.application.test_run_search import Source
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import IZTAPALAPA, FakeRegionRepository

pytestmark = pytest.mark.anyio

ACCOUNT = ("searchapi", "searchapi_web")


def test_las_dos_fuentes_de_searchapi_son_una_cuenta() -> None:
    assert credit_account(Provider.SEARCHAPI) == credit_account(Provider.SEARCHAPI_WEB)
    assert account_providers(Provider.SEARCHAPI_WEB) == (Provider.SEARCHAPI, Provider.SEARCHAPI_WEB)
    assert account_label(Provider.SEARCHAPI_WEB) == "SearchApi (noticias + web)"
    # Una fuente gratis es su propia «cuenta».
    assert account_providers(Provider.GDELT) == (Provider.GDELT,)


async def test_lo_gastado_y_el_tope_se_cuentan_para_las_dos() -> None:
    news = FakeProvider(Provider.SEARCHAPI, cost=1)
    web = FakeProvider(Provider.SEARCHAPI_WEB, cost=1)
    # Queda 1 crédito en el mes: solo cabe una de las dos consultas.
    execute, _, log = use_case(news, web, log=FakeLog(used=99), monthly_limit=100)

    result = await execute.execute([planned(Provider.SEARCHAPI), planned(Provider.SEARCHAPI_WEB)])

    assert log.asked_providers == [ACCOUNT]
    assert (news.calls + web.calls, result.credits_used) == (1, 1)
    [skipped] = [o for o in result.outcomes if o.status == "skipped"]
    assert skipped.message == (
        "Se alcanzó el tope mensual de créditos de SearchApi (noticias + web) (100)."
    )
    assert result.status is ExecutionStatus.PARTIAL


# Cambió el requisito (revisión del 18/11/2026): sin saldo a media búsqueda,
# Google web no vuelve «parcial» la búsqueda si las demás fuentes respondieron;
# lo dice un aviso (``notice``) y el registro guarda el error real.
NO_CREDITS = "Google web no pudo buscar: sin créditos de SearchApi"
REJECTED_KEY = "Google web no pudo buscar: SearchApi rechazó la llave"


def no_credits(status: int = 429) -> ProviderNoCreditsError:
    return ProviderNoCreditsError(
        f"SearchApi no tiene créditos (HTTP {status}): No searches left",
        provider="searchapi_web",
        http_status=status,
    )


async def test_google_web_sin_saldo_a_media_busqueda_no_la_tumba() -> None:
    web = FakeProvider(Provider.SEARCHAPI_WEB, cost=1, error=no_credits())
    rss = FakeProvider(Provider.GOOGLE_NEWS_RSS)
    notices: list[tuple[UUID, str]] = []
    execute, cache, log = use_case(web, rss, on_notice=lambda s, n: notices.append((s, n)))
    search_id = uuid4()

    result = await execute.execute(
        [planned(Provider.SEARCHAPI_WEB), planned(Provider.GOOGLE_NEWS_RSS)], search_id
    )

    assert result.status is ExecutionStatus.COMPLETED
    assert len(result.articles) == 1
    [web_outcome] = [o for o in result.outcomes if o.query.provider is Provider.SEARCHAPI_WEB]
    assert (web_outcome.status, web_outcome.articles, web_outcome.message) == ("ok", (), None)
    assert web_outcome.notice == NO_CREDITS
    assert result.notice == NO_CREDITS
    assert notices == [(search_id, NO_CREDITS)]
    # Un error no se cobra ni se guarda en la caché; el registro dice lo que pasó.
    assert result.credits_used == 0
    assert cache.ttls == []
    [record] = [r for r in log.records if r.provider == "searchapi_web"]
    assert (record.status, record.http_status) == ("error", 429)
    assert record.error_message is not None and "No searches left" in record.error_message


async def test_llave_rechazada_tambien_es_un_aviso_y_no_una_falla() -> None:
    rejected = ProviderAuthError(
        "searchapi_web rechazó la llave (HTTP 401).", provider="searchapi_web", http_status=401
    )
    web = FakeProvider(Provider.SEARCHAPI_WEB, cost=1, error=rejected)
    execute, _, _ = use_case(web, FakeProvider(Provider.LOCAL_INDEX))

    result = await execute.execute([planned(Provider.SEARCHAPI_WEB), planned(Provider.LOCAL_INDEX)])

    assert (result.status, result.notice) == (ExecutionStatus.COMPLETED, REJECTED_KEY)


async def test_si_google_web_era_lo_unico_la_busqueda_falla_con_su_aviso() -> None:
    web = FakeProvider(Provider.SEARCHAPI_WEB, cost=1, error=no_credits(402))
    execute, _, _ = use_case(web)

    result = await execute.execute([planned(Provider.SEARCHAPI_WEB)])

    assert result.status is ExecutionStatus.FAILED
    [outcome] = result.outcomes
    assert (outcome.status, outcome.notice) == ("error", NO_CREDITS)
    assert outcome.message is not None and "HTTP 402" in outcome.message


async def test_un_error_de_una_fuente_gratis_sigue_siendo_parcial() -> None:
    # Un 403 del RSS no es un problema de saldo: la búsqueda queda parcial.
    blocked = ProviderAuthError(
        "google_news_rss rechazó la llave (HTTP 403).", provider="google_news_rss", http_status=403
    )
    rss = FakeProvider(Provider.GOOGLE_NEWS_RSS, error=blocked)
    execute, _, _ = use_case(rss, FakeProvider(Provider.LOCAL_INDEX))

    result = await execute.execute(
        [planned(Provider.GOOGLE_NEWS_RSS), planned(Provider.LOCAL_INDEX)]
    )

    assert (result.status, result.notice) == (ExecutionStatus.PARTIAL, None)


async def test_otro_error_de_google_web_sigue_siendo_parcial() -> None:
    broken = ProviderResponseError("Google web respondió raro.", provider="searchapi_web")
    web = FakeProvider(Provider.SEARCHAPI_WEB, cost=1, error=broken)
    execute, _, _ = use_case(web, FakeProvider(Provider.GOOGLE_NEWS_RSS))

    result = await execute.execute(
        [planned(Provider.SEARCHAPI_WEB), planned(Provider.GOOGLE_NEWS_RSS)]
    )

    assert (result.status, result.notice) == (ExecutionStatus.PARTIAL, None)


async def test_la_estimacion_cuenta_lo_gastado_por_toda_la_cuenta() -> None:
    repo = FakeConceptRepository()
    fgr = repo.add(concept("FGR"))
    log = FakeLog(used=40)
    plan = PlanSearch(
        concepts=repo,
        regions=FakeRegionRepository(),
        providers={
            Provider.SEARCHAPI: Source(Provider.SEARCHAPI, [], cost=1),
            Provider.SEARCHAPI_WEB: Source(Provider.SEARCHAPI_WEB, [], cost=1),
        },
        log=log,
        llm=OPENAI,
        llm_max_articles=150,
        credits_limit=41,
        now=lambda: NOW,
    )

    estimate = await plan.estimate(
        SearchRequest(
            "benji",
            (fgr.id,),
            IZTAPALAPA.id,
            WEEK,
            (Provider.SEARCHAPI, Provider.SEARCHAPI_WEB),
        )
    )

    assert log.asked_providers == [ACCOUNT]
    assert [q.provider for q in estimate.queries] == [Provider.SEARCHAPI, Provider.SEARCHAPI_WEB]
    assert (estimate.credits, estimate.credits_month, estimate.over_limit) == (2, 40, True)


async def test_la_busqueda_rapida_puede_traer_sus_propias_fuentes_por_defecto() -> None:
    repo = FakeConceptRepository()
    fgr = repo.add(concept("FGR"))
    plan = PlanSearch(
        concepts=repo,
        regions=FakeRegionRepository(),
        providers={
            p: Source(p, [], cost=1 if p is Provider.SEARCHAPI_WEB else 0)
            for p in (Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX, Provider.SEARCHAPI_WEB)
        },
        log=FakeLog(),
        llm=OPENAI,
        llm_max_articles=150,
        credits_limit=100,
        default_sources=(Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX),
        now=lambda: NOW,
    )
    manual = SearchRequest("benji", (fgr.id,), IZTAPALAPA.id, WEEK)

    assert (await plan.estimate(manual)).search.providers == (
        Provider.GOOGLE_NEWS_RSS,
        Provider.LOCAL_INDEX,
    )
    quick = SearchRequest(
        "benji",
        (fgr.id,),
        IZTAPALAPA.id,
        WEEK,
        default_sources=(Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX, Provider.SEARCHAPI_WEB),
    )
    assert Provider.SEARCHAPI_WEB in (await plan.estimate(quick)).search.providers
