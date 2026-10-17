"""PlanSearch: consultas y costo antes de gastar, con piezas en memoria."""

from datetime import UTC, date, datetime

import pytest

from app.application.ports.llm import LLMInfo
from app.application.use_cases.plan_search import PlanSearch, SearchRequest
from app.domain.concept import ConceptDraft
from app.domain.errors import ConceptNotFoundError, InvalidRequestError, RegionNotFoundError
from app.domain.queries import DateWindow, Provider
from tests.unit.application.test_execute_queries import FakeLog
from tests.unit.application.test_run_search import Source
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import IZTAPALAPA, FakeRegionRepository

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 17, 18, tzinfo=UTC)
WEEK = DateWindow.last_days(7, date(2026, 10, 17))
OPENAI = LLMInfo("openai", "gpt-6-luna", 0.10, 0.50, configured=True)


def concept(name: str, *, active: bool = True) -> ConceptDraft:
    return ConceptDraft.validated(
        name=name,
        description=f"Notas de {name.lower()}",
        keywords=(name.lower(),),
        exclude_terms=("simulacro",),
        color="#AA0000",
        is_active=active,
    )


def planner(
    concepts: FakeConceptRepository,
    *,
    searchapi: bool = True,
    used: int = 10,
    limit: int = 100,
) -> PlanSearch:
    sources = [
        Source(Provider.SEARCHAPI, [], cost=1, configured=searchapi),
        Source(Provider.LOCAL_INDEX, []),
    ]
    return PlanSearch(
        concepts=concepts,
        regions=FakeRegionRepository(),
        providers={s.provider: s for s in sources},
        log=FakeLog(used=used),
        llm=OPENAI,
        llm_max_articles=150,
        credits_limit=limit,
        now=lambda: NOW,
    )


async def test_estima_consultas_creditos_y_costo_maximo() -> None:
    repo = FakeConceptRepository()
    extorsion = repo.add(concept("Extorsión"))
    secuestro = repo.add(concept("Secuestro"))

    estimate = await planner(repo).estimate(
        SearchRequest("benji", (extorsion.id, secuestro.id), IZTAPALAPA.id, WEEK)
    )

    # Un concepto por consulta, con cada proveedor configurado.
    assert [(q.provider, q.keywords) for q in estimate.queries] == [
        (Provider.SEARCHAPI, ("extorsión",)),
        (Provider.LOCAL_INDEX, ("extorsión",)),
        (Provider.SEARCHAPI, ("secuestro",)),
        (Provider.LOCAL_INDEX, ("secuestro",)),
    ]
    assert (estimate.credits, estimate.credits_month, estimate.credits_limit) == (2, 10, 100)
    assert estimate.llm_max_cost_usd == pytest.approx(0.0525)
    assert estimate.breadcrumb == "México › Ciudad de México › Iztapalapa"
    assert not estimate.over_limit
    search = estimate.search
    assert (search.user_id, search.region_id, search.queries_planned) == ("benji", 3, 4)
    assert (search.date_from, search.date_to, search.credits_estimated) == (
        date(2026, 10, 10),
        date(2026, 10, 17),
        2,
    )
    assert next((c.name, c.description, c.exclude_terms) for c in search.concepts) == (
        "Extorsión",
        "Notas de extorsión",
        ("simulacro",),
    )


async def test_sin_searchapi_es_gratis_y_el_tope_avisa() -> None:
    repo = FakeConceptRepository()
    extorsion = repo.add(concept("Extorsión"))
    request = SearchRequest("benji", (extorsion.id,), IZTAPALAPA.id, WEEK)

    free = await planner(repo, searchapi=False).estimate(request)
    full = await planner(repo, used=100).estimate(request)

    assert [q.provider for q in free.queries] == [Provider.LOCAL_INDEX]
    assert free.credits == 0
    assert full.over_limit


async def test_conceptos_y_region_invalidos() -> None:
    repo = FakeConceptRepository()
    extorsion = repo.add(concept("Extorsión"))
    apagado = repo.add(concept("Apagado", active=False))
    use = planner(repo)

    with pytest.raises(InvalidRequestError, match="al menos un concepto"):
        await use.estimate(SearchRequest("benji", (), IZTAPALAPA.id, WEEK))
    with pytest.raises(InvalidRequestError, match="repetido"):
        await use.estimate(SearchRequest("benji", (extorsion.id,) * 2, IZTAPALAPA.id, WEEK))
    with pytest.raises(InvalidRequestError, match="desactivado"):
        await use.estimate(SearchRequest("benji", (apagado.id,), IZTAPALAPA.id, WEEK))
    with pytest.raises(ConceptNotFoundError):
        await use.estimate(SearchRequest("benji", (999,), IZTAPALAPA.id, WEEK))
    with pytest.raises(RegionNotFoundError):
        await use.estimate(SearchRequest("benji", (extorsion.id,), 999, WEEK))
