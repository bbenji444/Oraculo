"""Búsqueda rápida: de un texto libre a una búsqueda con un concepto oculto (ADR-0110)."""

from dataclasses import replace

import pytest

from app.application.audit import CONCEPT_CREATED, CONCEPT_TERMS_SUGGESTED, CONCEPT_UPDATED
from app.application.use_cases.concepts import ListConcepts
from app.application.use_cases.plan_search import PlanSearch
from app.application.use_cases.quick_search import (
    QUICK_COLOR,
    KeepQuickConcept,
    QuickSearchRequest,
    StartQuickSearch,
    quick_name,
)
from app.application.use_cases.start_search import StartSearch
from app.application.use_cases.suggest_terms import SuggestConceptTerms
from app.domain.concept import NAME_MAX_LENGTH, QueryMode
from app.domain.errors import ConceptNameTakenError, ConceptNotFoundError, LLMNotConfiguredError
from app.domain.queries import Provider
from tests.unit.application.test_execute_queries import FakeLog
from tests.unit.application.test_plan_search import OPENAI, WEEK, concept
from tests.unit.application.test_run_search import Source
from tests.unit.application.test_start_search import CAPS, Queue, Store
from tests.unit.application.test_suggest_terms import ACTOR, PRICES, FakeSuggester, result
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import IZTAPALAPA, FakeRegionRepository

pytestmark = pytest.mark.anyio

TEXT = "hackeos y filtraciones de bases de datos del gobierno"


def quick(
    repo: FakeConceptRepository, *, configured: bool = True
) -> tuple[StartQuickSearch, Store, Queue]:
    planner = PlanSearch(
        concepts=repo,
        regions=FakeRegionRepository(),
        # Solo el índice local: la prueba no depende de créditos.
        providers={Provider.LOCAL_INDEX: Source(Provider.LOCAL_INDEX, [])},
        log=FakeLog(),
        llm=replace(OPENAI, configured=configured),
        llm_max_articles=150,
        credits_limit=100,
    )
    store, queue = Store(), Queue()
    suggester = SuggestConceptTerms(
        FakeSuggester(result("filtran datos", "hackeo gobierno")), PRICES, repo
    )
    use = StartQuickSearch(suggester, repo, StartSearch(planner, store, queue, CAPS))
    return use, store, queue


async def test_crea_un_concepto_oculto_y_lanza_la_busqueda() -> None:
    repo = FakeConceptRepository()
    use, store, queue = quick(repo)

    started = await use.execute(QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK), ACTOR)

    hidden = started.concept
    assert hidden.is_quick
    assert (hidden.data.name, hidden.data.description, hidden.data.keywords) == (
        "Hackeos a gobierno",
        TEXT,
        ("filtran datos", "hackeo gobierno"),
    )
    assert (hidden.data.query_mode, hidden.data.color) == (QueryMode.OPEN, QUICK_COLOR)
    assert queue.sent == [started.search.search_id]
    [created] = store.created
    assert created.user_id == "benji"
    # No sale en la lista de conceptos.
    assert (await ListConcepts(repo).execute()).items == ()
    actions = [entry.action for _, entry in repo.audit]
    assert actions == [CONCEPT_TERMS_SUGGESTED, CONCEPT_CREATED]
    assert repo.audit[1][1].payload["busqueda_rapida"] is True


async def test_no_choca_con_el_nombre_de_un_concepto_guardado() -> None:
    repo = FakeConceptRepository()
    repo.add(concept("Hackeos a gobierno"))
    use, _, _ = quick(repo)

    started = await use.execute(QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK), ACTOR)

    assert started.concept.data.name == "Hackeos a gobierno"


async def test_si_la_busqueda_no_se_puede_lanzar_el_error_llega_igual() -> None:
    use, store, queue = quick(FakeConceptRepository(), configured=False)

    with pytest.raises(LLMNotConfiguredError):
        await use.execute(QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK), ACTOR)

    assert (store.created, queue.sent) == ([], [])


def test_el_nombre_sale_del_texto_si_la_ia_no_dio_uno() -> None:
    assert quick_name("Robo de autos", "x") == "Robo de autos"
    assert quick_name("", "  robo de autos   en Jalisco ") == "robo de autos en Jalisco"
    long = quick_name("", "palabra " * 30)
    assert len(long) <= NAME_MAX_LENGTH
    assert long.endswith("palabra")


async def test_guardar_como_concepto_lo_vuelve_visible() -> None:
    repo = FakeConceptRepository()
    hidden = repo.add(concept("Robo de autos"), quick=True)

    kept = await KeepQuickConcept(repo).execute(hidden.id, ACTOR)

    assert not kept.is_quick
    assert [c.id for c in (await ListConcepts(repo).execute()).items] == [hidden.id]
    [(_, entry)] = repo.audit
    assert entry.action == CONCEPT_UPDATED
    before, after = entry.payload["before"], entry.payload["after"]
    assert isinstance(before, dict) and isinstance(after, dict)
    assert (before["is_quick"], after["is_quick"], after["name"]) == (True, False, "Robo de autos")


async def test_guardar_avisa_si_el_nombre_ya_existe() -> None:
    repo = FakeConceptRepository()
    repo.add(concept("Robo de autos"))
    hidden = repo.add(concept("Robo de autos"), quick=True)

    with pytest.raises(ConceptNameTakenError, match="Cambia el nombre"):
        await KeepQuickConcept(repo).execute(hidden.id, ACTOR)


async def test_solo_se_guardan_las_busquedas_rapidas() -> None:
    repo = FakeConceptRepository()
    saved = repo.add(concept("Extorsión"))

    with pytest.raises(ConceptNotFoundError):
        await KeepQuickConcept(repo).execute(saved.id, ACTOR)
    with pytest.raises(ConceptNotFoundError):
        await KeepQuickConcept(repo).execute(999, ACTOR)
