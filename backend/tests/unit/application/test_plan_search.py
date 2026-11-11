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
        date(2026, 10, 11),  # 7 días contando hoy (11/11/2026)
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


async def test_las_fuentes_elegidas_mandan_y_se_guardan() -> None:
    # Switches (F12.2, ADR-0027): con solo el índice local la búsqueda es gratis.
    repo = FakeConceptRepository()
    extorsion = repo.add(concept("Extorsión"))
    request = SearchRequest(
        "benji", (extorsion.id,), IZTAPALAPA.id, WEEK, providers=(Provider.LOCAL_INDEX,)
    )

    estimate = await planner(repo).estimate(request)

    assert [q.provider for q in estimate.queries] == [Provider.LOCAL_INDEX]
    assert estimate.credits == 0
    assert estimate.search.providers == (Provider.LOCAL_INDEX,)


async def test_sin_elegir_se_usan_las_de_por_defecto() -> None:
    repo = FakeConceptRepository()
    extorsion = repo.add(concept("Extorsión"))
    plan = PlanSearch(
        concepts=repo,
        regions=FakeRegionRepository(),
        providers={
            p: Source(p, [], cost=1 if p is Provider.SEARCHAPI else 0)
            for p in (Provider.SEARCHAPI, Provider.LOCAL_INDEX)
        },
        log=FakeLog(used=0),
        llm=OPENAI,
        llm_max_articles=150,
        credits_limit=100,
        default_sources=(Provider.LOCAL_INDEX, Provider.GOOGLE_NEWS_RSS),
        now=lambda: NOW,
    )

    estimate = await plan.estimate(SearchRequest("benji", (extorsion.id,), IZTAPALAPA.id, WEEK))

    # El RSS está en la lista por defecto pero no configurado aquí: se omite.
    assert estimate.search.providers == (Provider.LOCAL_INDEX,)


@pytest.mark.parametrize(
    ("providers", "message"),
    [
        ((), "Elige al menos una fuente"),
        ((Provider.SEARCHAPI,), r"SearchApi \(Google News\): no está configurada"),
        ((Provider.GDELT,), "no se puede elegir"),
    ],
)
async def test_fuentes_invalidas_no_se_planean(
    providers: tuple[Provider, ...], message: str
) -> None:
    repo = FakeConceptRepository()
    extorsion = repo.add(concept("Extorsión"))
    request = SearchRequest("benji", (extorsion.id,), IZTAPALAPA.id, WEEK, providers=providers)

    with pytest.raises(InvalidRequestError, match=message):
        await planner(repo, searchapi=False).estimate(request)


def test_probar_concepto_no_muestra_fuentes_ocultas() -> None:
    # BrowserWork configurado pero oculto (ADR-0028): no aparece en lo ofrecido.
    repo = FakeConceptRepository()
    plan = PlanSearch(
        concepts=repo,
        regions=FakeRegionRepository(),
        providers={
            p: Source(p, [])
            for p in (Provider.SEARCHAPI, Provider.LOCAL_INDEX, Provider.BROWSERWORK_BING)
        },
        log=FakeLog(used=0),
        llm=OPENAI,
        llm_max_articles=150,
        credits_limit=100,
    )

    assert Provider.BROWSERWORK_BING in plan.available_providers()
    assert plan.offered_providers() == (Provider.SEARCHAPI, Provider.LOCAL_INDEX)


# --- Subdivisiones (02/11/2026) ---

HOMICIDIO_ID = 5


def topic(name: str, keywords: tuple[str, ...], *, active: bool = True) -> ConceptDraft:
    return ConceptDraft.validated(
        name=name,
        description=f"Tema general: {name.lower()}",
        keywords=keywords,
        exclude_terms=("película",),
        color="#FF4D6D",
        is_active=active,
    )


async def test_fgr_con_subdivision_pide_ambas_palabras() -> None:
    repo = FakeConceptRepository()
    fgr = repo.add(concept("FGR"))
    repo.add(topic("Homicidio", ("homicidio", "asesinato")), category_id=HOMICIDIO_ID)

    estimate = await planner(repo).estimate(
        SearchRequest("benji", (fgr.id,), IZTAPALAPA.id, WEEK, category_ids=(HOMICIDIO_ID,))
    )

    [copied] = estimate.search.concepts
    assert copied.keywords == ("fgr",)
    assert copied.topic_terms == ("homicidio", "asesinato")
    assert copied.category_ids == (HOMICIDIO_ID,)
    # Las exclusiones del tema también se aplican.
    assert copied.exclude_terms == ("simulacro", "película")
    assert {q.topic_terms for q in estimate.queries} == {("homicidio", "asesinato")}


async def test_un_tema_general_se_busca_solo_y_no_se_le_agrega_otra_subdivision() -> None:
    repo = FakeConceptRepository()
    fgr = repo.add(concept("FGR"))
    homicidio = repo.add(topic("Homicidio", ("homicidio",)), category_id=HOMICIDIO_ID)
    repo.add(topic("Secuestro", ("secuestro",)), category_id=3)
    use = planner(repo)

    solo = await use.estimate(SearchRequest("benji", (homicidio.id,), IZTAPALAPA.id, WEEK))
    mixed = await use.estimate(
        SearchRequest("benji", (fgr.id, homicidio.id), IZTAPALAPA.id, WEEK, category_ids=(3,))
    )

    assert [(c.keywords, c.topic_terms) for c in solo.search.concepts] == [(("homicidio",), ())]
    assert [(c.name, c.topic_terms) for c in mixed.search.concepts] == [
        ("FGR", ("secuestro",)),
        ("Homicidio", ()),
    ]


async def test_varias_subdivisiones_se_juntan_sin_repetir_palabras() -> None:
    repo = FakeConceptRepository()
    fgr = repo.add(concept("FGR"))
    repo.add(topic("Homicidio", ("homicidio", "ataque armado")), category_id=HOMICIDIO_ID)
    repo.add(topic("Armas", ("ataque armado", "granada")), category_id=6)

    estimate = await planner(repo).estimate(
        SearchRequest("benji", (fgr.id,), IZTAPALAPA.id, WEEK, category_ids=(HOMICIDIO_ID, 6))
    )

    [copied] = estimate.search.concepts
    assert copied.topic_terms == ("homicidio", "ataque armado", "granada")
    assert copied.exclude_terms == ("simulacro", "película")


async def test_subdivisiones_invalidas() -> None:
    repo = FakeConceptRepository()
    fgr = repo.add(concept("FGR"))
    homicidio = repo.add(topic("Homicidio", ("homicidio",)), category_id=HOMICIDIO_ID)
    repo.add(topic("Apagada", ("apagada",), active=False), category_id=9)
    use = planner(repo)

    def request(ids: tuple[int, ...], categories: tuple[int, ...]) -> SearchRequest:
        return SearchRequest("benji", ids, IZTAPALAPA.id, WEEK, category_ids=categories)

    with pytest.raises(InvalidRequestError, match="repetida"):
        await use.estimate(request((fgr.id,), (HOMICIDIO_ID, HOMICIDIO_ID)))
    with pytest.raises(InvalidRequestError, match="no tiene palabras clave"):
        await use.estimate(request((fgr.id,), (999,)))
    with pytest.raises(InvalidRequestError, match="no tiene palabras clave"):
        await use.estimate(request((fgr.id,), (9,)))
    with pytest.raises(InvalidRequestError, match="no solas"):
        await use.estimate(request((homicidio.id,), (HOMICIDIO_ID,)))
