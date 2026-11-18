"""Búsqueda rápida: de un texto libre a una búsqueda con un concepto oculto (ADR-0110, ADR-0113)."""

from dataclasses import replace

import pytest

from app.application.audit import CONCEPT_CREATED, CONCEPT_TERMS_SUGGESTED, CONCEPT_UPDATED
from app.application.ports.llm import TermSuggestionResult
from app.application.use_cases.concepts import ListConcepts
from app.application.use_cases.plan_search import PlanSearch
from app.application.use_cases.quick_search import (
    QUICK_COLOR,
    KeepQuickConcept,
    QuickSearchRequest,
    StartQuickSearch,
    names_whole_world,
    quick_name,
    resolve_place,
)
from app.application.use_cases.start_search import StartSearch
from app.application.use_cases.suggest_terms import SuggestConceptTerms
from app.domain.concept import NAME_MAX_LENGTH, QueryMode
from app.domain.errors import ConceptNameTakenError, ConceptNotFoundError, LLMNotConfiguredError
from app.domain.queries import Provider
from app.domain.region import RegionLevel
from app.domain.term_suggestions import EmptySuggestionError
from tests.unit.application.test_execute_queries import FakeLog
from tests.unit.application.test_plan_search import OPENAI, WEEK, concept
from tests.unit.application.test_run_search import Source
from tests.unit.application.test_start_search import CAPS, Queue, Store
from tests.unit.application.test_suggest_terms import ACTOR, PRICES, FakeSuggester, result
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import (
    ALL,
    CDMX,
    CUAUHTEMOC,
    IZTAPALAPA,
    MEXICO,
    FakeRegionRepository,
    make_region,
)

pytestmark = pytest.mark.anyio

TEXT = "hackeos y filtraciones de bases de datos del gobierno"


# Un Cuauhtémoc en otro estado, para el nombre repetido.
CHIHUAHUA = make_region(
    10, "Chihuahua", RegionLevel.STATE, parent_id=1, code="08", prefix="Entidad federativa"
)
CUAUHTEMOC_CHIH = make_region(11, "Cuauhtémoc", parent_id=10, code="08017")
# «Mundo» (ADR-0112), para las búsquedas en todo el mundo.
WORLD = make_region(12, "Mundo", RegionLevel.WORLD, code="WLD", prefix="")
# Estados para el lugar que se quita del literal (ADR-0113).
JALISCO = make_region(
    13, "Jalisco", RegionLevel.STATE, parent_id=1, code="14", prefix="Entidad federativa"
)
SINALOA = make_region(
    14, "Sinaloa", RegionLevel.STATE, parent_id=1, code="25", prefix="Entidad federativa"
)
REGIONS = (*ALL, CHIHUAHUA, CUAUHTEMOC_CHIH, WORLD, JALISCO, SINALOA)


def quick(
    repo: FakeConceptRepository,
    *,
    configured: bool = True,
    place: str | None = None,
    place_state: str | None = None,
    answer: TermSuggestionResult | None = None,
) -> tuple[StartQuickSearch, Store, Queue]:
    regions = FakeRegionRepository(REGIONS)
    planner = PlanSearch(
        concepts=repo,
        regions=regions,
        # Solo el índice local: la prueba no depende de créditos.
        providers={Provider.LOCAL_INDEX: Source(Provider.LOCAL_INDEX, [])},
        log=FakeLog(),
        llm=replace(OPENAI, configured=configured),
        llm_max_articles=150,
        credits_limit=100,
    )
    store, queue = Store(), Queue()
    suggester = SuggestConceptTerms(
        FakeSuggester(
            answer
            or result("filtran datos", "hackeo gobierno", place=place, place_state=place_state)
        ),
        PRICES,
        repo,
    )
    use = StartQuickSearch(suggester, repo, StartSearch(planner, store, queue, CAPS), regions)
    return use, store, queue


async def test_crea_un_concepto_oculto_y_lanza_la_busqueda() -> None:
    repo = FakeConceptRepository()
    use, store, queue = quick(repo)

    started = await use.execute(QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK), ACTOR)

    hidden = started.concept
    assert hidden.is_quick
    # ADR-0113: el texto del analista es el nombre y la primera frase; la IA
    # («Hackeos a gobierno») ya no lo renombra.
    assert (hidden.data.name, hidden.data.description, hidden.data.keywords) == (
        TEXT,
        TEXT,
        (TEXT, "filtran datos", "hackeo gobierno"),
    )
    assert hidden.data.required_terms == ()
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
    repo.add(concept(TEXT))
    use, _, _ = quick(repo)

    started = await use.execute(QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK), ACTOR)

    assert started.concept.data.name == TEXT


async def test_si_la_busqueda_no_se_puede_lanzar_el_error_llega_igual() -> None:
    use, store, queue = quick(FakeConceptRepository(), configured=False)

    with pytest.raises(LLMNotConfiguredError):
        await use.execute(QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK), ACTOR)

    assert (store.created, queue.sent) == ([], [])


def test_el_nombre_es_el_literal_o_si_no_hay_el_texto() -> None:
    # ADR-0113: el primer argumento ya no es el nombre de la IA sino el literal.
    assert quick_name("hacker eternal", "x") == "hacker eternal"
    assert quick_name(None, "  robo de autos   en Jalisco ") == "robo de autos en Jalisco"
    assert quick_name("", "robo de autos") == "robo de autos"
    long = quick_name(None, "palabra " * 30)
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


async def test_busca_en_el_lugar_que_nombra_el_texto() -> None:
    use, store, _ = quick(FakeConceptRepository(), place="Ciudad de México")

    started = await use.execute(QuickSearchRequest("benji", TEXT, MEXICO.id, WEEK), ACTOR)

    assert started.place_region == CDMX
    [created] = store.created
    assert created.region_id == CDMX.id


async def test_sin_lugar_en_el_texto_usa_la_region_elegida() -> None:
    use, store, _ = quick(FakeConceptRepository())

    started = await use.execute(QuickSearchRequest("benji", TEXT, IZTAPALAPA.id, WEEK), ACTOR)

    assert started.place_region is None
    [created] = store.created
    assert created.region_id == IZTAPALAPA.id


async def test_un_lugar_que_no_esta_en_el_catalogo_usa_la_region_elegida() -> None:
    use, store, _ = quick(FakeConceptRepository(), place="Narnia")

    started = await use.execute(QuickSearchRequest("benji", TEXT, MEXICO.id, WEEK), ACTOR)

    assert started.place_region is None
    [created] = store.created
    assert created.region_id == MEXICO.id


async def test_el_nombre_repetido_se_decide_por_el_estado() -> None:
    regions = FakeRegionRepository(REGIONS)

    assert await resolve_place(regions, "Cuauhtémoc", "Chihuahua") == CUAUHTEMOC_CHIH
    assert await resolve_place(regions, "cuauhtemoc", "Ciudad de México") == CUAUHTEMOC
    # Sin estado, o con uno que no cuadra, el primero del catálogo.
    assert await resolve_place(regions, "Cuauhtémoc", None) == CUAUHTEMOC
    assert await resolve_place(regions, "Cuauhtémoc", "Sonora") == CUAUHTEMOC


async def test_un_parecido_no_cuenta_como_lugar() -> None:
    regions = FakeRegionRepository(REGIONS)

    # "Iztapa" está dentro de "Iztapalapa", pero no es ese lugar.
    assert await resolve_place(regions, "Iztapa", None) is None
    assert await resolve_place(regions, None, "Jalisco") is None
    assert await resolve_place(regions, "", None) is None


@pytest.mark.parametrize(
    "text",
    [
        "bases de datos hackeadas en todo el mundo",
        "Ataques de ransomware a nivel mundial",
        "fraudes con criptomonedas a nivel global",
        "filtraciones de datos en el mundo",
        "secuestros en todos los países",
    ],
)
def test_reconoce_cuando_se_pide_todo_el_mundo(text: str) -> None:
    assert names_whole_world(text)


@pytest.mark.parametrize(
    "text",
    [TEXT, "boletos para el Mundial", "Mundial de futbol 2026 en Guadalajara", "mundialista"],
)
def test_no_confunde_el_mundial_ni_un_texto_sin_mundo(text: str) -> None:
    assert not names_whole_world(text)


async def test_en_todo_el_mundo_busca_en_mundo() -> None:
    use, store, _ = quick(FakeConceptRepository())
    text = "bases de datos hackeadas en todo el mundo"

    started = await use.execute(QuickSearchRequest("benji", text, MEXICO.id, WEEK), ACTOR)

    assert started.place_region == WORLD
    [created] = store.created
    assert created.region_id == WORLD.id


async def test_un_lugar_del_catalogo_gana_sobre_en_el_mundo() -> None:
    use, store, _ = quick(FakeConceptRepository(), place="Ciudad de México")
    text = "robo de autos en la Ciudad de México, de los más altos en el mundo"

    started = await use.execute(QuickSearchRequest("benji", text, MEXICO.id, WEEK), ACTOR)

    assert started.place_region == CDMX
    [created] = store.created
    assert created.region_id == CDMX.id


# --- El texto se busca tal cual (ADR-0113) ---


def eternal(
    *phrases: str, name: str = "Hackeo Eternal", entities: tuple[str, ...] = ("Eternal",)
) -> TermSuggestionResult:
    """Lo que respondió la IA real el 18/11/2026, con las entidades de terms_v3."""
    return result(*phrases, excludes=(), name=name, entities=entities)


async def test_hacker_eternal_busca_el_texto_tal_cual_y_no_lo_renombra() -> None:
    # Benji, 18/11/2026: buscó «hacker eternal» en todo el mundo; la IA lo
    # volvió «Hackeo Eternal», nunca se mandó «hacker eternal» y salieron 0.
    answer = eternal("hackean Eternal", "hackeo Eternal", "hackers Eternal")
    use, _, _ = quick(FakeConceptRepository(), answer=answer)

    started = await use.execute(
        QuickSearchRequest("benji", "hacker eternal", WORLD.id, WEEK), ACTOR
    )

    data = started.concept.data
    assert data.keywords[0] == "hacker eternal"
    assert data.name == "hacker eternal"
    assert data.keywords == (
        "hacker eternal",
        "hackean Eternal",
        "hackeo Eternal",
        "hackers Eternal",
    )
    # El nombre propio con la grafía de la persona, para el juicio de la IA.
    assert data.required_terms == ("eternal",)


async def test_hacker_eternal_conserva_las_mayusculas() -> None:
    use, _, _ = quick(FakeConceptRepository(), answer=eternal("hackeo Eternal"))

    started = await use.execute(
        QuickSearchRequest("benji", "Hacker Eternal", WORLD.id, WEEK), ACTOR
    )

    assert started.concept.data.name == "Hacker Eternal"
    assert started.concept.data.keywords[0] == "Hacker Eternal"
    assert started.concept.data.required_terms == ("Eternal",)


async def test_si_la_ia_quita_el_nombre_propio_el_literal_sigue_primero() -> None:
    # Concepto 34 de la VM: con «eternal hacker» la IA dio frases sin Eternal
    # («hackean sistemas») y trajo 122 notas de ciberataques cualquiera.
    answer = eternal("hackean sistemas", "roban datos", name="Hackeos")
    use, _, _ = quick(FakeConceptRepository(), answer=answer)

    started = await use.execute(
        QuickSearchRequest("benji", "eternal hacker", WORLD.id, WEEK), ACTOR
    )

    assert started.concept.data.keywords == ("eternal hacker",)


async def test_si_la_ia_no_reconoce_el_nombre_el_literal_va_primero_igual() -> None:
    answer = eternal("hackean sistemas", "roban datos", name="Hackeos", entities=())
    use, _, _ = quick(FakeConceptRepository(), answer=answer)

    started = await use.execute(
        QuickSearchRequest("benji", "eternal hacker", WORLD.id, WEEK), ACTOR
    )

    assert started.concept.data.keywords == ("eternal hacker", "hackean sistemas", "roban datos")
    assert started.concept.data.required_terms == ()


async def test_entidad_que_no_esta_en_el_texto_no_se_exige() -> None:
    # La IA «corrige» hacker a hackeo: eso no lo escribió la persona.
    answer = eternal("hackeo Eternal", entities=("Hackeo",))
    use, _, _ = quick(FakeConceptRepository(), answer=answer)

    started = await use.execute(
        QuickSearchRequest("benji", "hacker eternal", WORLD.id, WEEK), ACTOR
    )

    assert started.concept.data.required_terms == ()
    assert started.concept.data.keywords == ("hacker eternal", "hackeo Eternal")


async def test_el_literal_quita_el_lugar_y_todo_el_mundo() -> None:
    use, store, _ = quick(FakeConceptRepository(), place="Jalisco")

    started = await use.execute(
        QuickSearchRequest("benji", "robo de autos en Jalisco", MEXICO.id, WEEK), ACTOR
    )

    assert started.concept.data.keywords[0] == "robo de autos"
    assert started.concept.data.name == "robo de autos"
    [created] = store.created
    assert created.region_id == JALISCO.id

    use, _, _ = quick(FakeConceptRepository())
    world = await use.execute(
        QuickSearchRequest("benji", "bases de datos hackeadas en todo el mundo", MEXICO.id, WEEK),
        ACTOR,
    )

    assert world.concept.data.keywords[0] == "bases de datos hackeadas"


async def test_cartel_de_sinaloa_no_pierde_de_sinaloa() -> None:
    # Aunque la IA diga que el lugar es Sinaloa, «de Sinaloa» es parte del nombre.
    use, _, _ = quick(FakeConceptRepository(), place="Sinaloa")

    started = await use.execute(
        QuickSearchRequest("benji", "ataques del Cártel de Sinaloa", MEXICO.id, WEEK), ACTOR
    )

    assert started.concept.data.keywords[0] == "ataques del Cártel de Sinaloa"


async def test_un_texto_de_mas_de_80_caracteres_se_busca_tal_cual() -> None:
    # Revisión del 18/11/2026 (hallazgo 7): antes, de 80 caracteres para arriba
    # no había literal y solo se buscaban las frases de la IA.
    text = (
        "hackeos y filtraciones de bases de datos de dependencias del gobierno federal "
        "y de los estados"
    )
    use, store, _ = quick(FakeConceptRepository())

    started = await use.execute(QuickSearchRequest("benji", text, MEXICO.id, WEEK), ACTOR)

    assert started.concept.data.keywords == (text, "filtran datos", "hackeo gobierno")
    assert len(started.concept.data.name) <= NAME_MAX_LENGTH
    assert text.startswith(started.concept.data.name)
    assert len(store.created) == 1


async def test_literal_que_no_cabe_en_google_no_se_agrega_pero_la_busqueda_sale() -> None:
    # Más de 32 palabras (el tope de Google): no hay literal.
    text = " ".join(["hackeos a dependencias del gobierno federal"] * 7)
    use, store, _ = quick(FakeConceptRepository())

    started = await use.execute(QuickSearchRequest("benji", text, MEXICO.id, WEEK), ACTOR)

    assert started.concept.data.keywords == ("filtran datos", "hackeo gobierno")
    assert len(started.concept.data.name) <= NAME_MAX_LENGTH
    assert len(store.created) == 1


@pytest.mark.parametrize("text", ["Pemex", "LockBit", "IA"])
async def test_un_nombre_solo_se_busca(text: str) -> None:
    # Revisión del 18/11/2026 (hallazgo 7): con menos de 10 caracteres se
    # rechazaba; en Google basta escribir «Pemex».
    answer = eternal(f"{text} filtra", f"hackean {text}", name=text, entities=(text,))
    use, store, _ = quick(FakeConceptRepository(), answer=answer)

    started = await use.execute(QuickSearchRequest("benji", text, MEXICO.id, WEEK), ACTOR)

    assert started.concept.data.keywords[0] == text
    assert started.concept.data.name == text
    assert started.concept.data.required_terms == (text,)
    assert len(store.created) == 1


async def test_sin_literal_ni_frases_con_el_nombre_es_error_claro() -> None:
    # Más de 32 palabras (el tope de Google): no hay literal.
    text = " ".join(["todo lo que ha hecho el hacker eternal con las bases de datos"] * 3)
    answer = eternal("hackean sistemas", name="Hackeos")
    repo = FakeConceptRepository()
    use, store, _ = quick(repo, answer=answer)

    with pytest.raises(EmptySuggestionError, match="más corto"):
        await use.execute(QuickSearchRequest("benji", text, MEXICO.id, WEEK), ACTOR)

    assert store.created == []
    assert [entry.action for _, entry in repo.audit] == [CONCEPT_TERMS_SUGGESTED]


# --- Un lugar no es nombre propio (revisión del 18/11/2026, hallazgo 3) ---

ROBO_PHRASES = (
    "roban autos con violencia",
    "robo de vehículos con violencia",
    "asaltan automovilistas",
)


async def test_jalisco_como_entidad_no_se_exige_ni_protege_el_lugar() -> None:
    # rv25_sim.py: con entities=["Jalisco"] el literal se quedaba con «en
    # Jalisco», las frases de la IA se tiraban y se exigía «Jalisco».
    answer = result(*ROBO_PHRASES, place="Jalisco", entities=("Jalisco",))
    use, store, _ = quick(FakeConceptRepository(), answer=answer)

    started = await use.execute(
        QuickSearchRequest("benji", "robo de autos con violencia en Jalisco", MEXICO.id, WEEK),
        ACTOR,
    )

    data = started.concept.data
    assert data.required_terms == ()
    assert data.keywords == ("robo de autos con violencia", *ROBO_PHRASES)
    [created] = store.created
    assert created.region_id == JALISCO.id


async def test_el_alias_del_lugar_tampoco_es_entidad() -> None:
    # La IA dice «Ciudad de México» y marca «CDMX» (su alias) como nombre propio.
    answer = result(*ROBO_PHRASES, place="Ciudad de México", entities=("CDMX", "Eternal"))
    use, _, _ = quick(FakeConceptRepository(), answer=answer)

    started = await use.execute(
        QuickSearchRequest("benji", "robo de autos del hacker Eternal en CDMX", MEXICO.id, WEEK),
        ACTOR,
    )

    data = started.concept.data
    assert data.required_terms == ("Eternal",)
    assert data.keywords[0] == "robo de autos del hacker Eternal"
