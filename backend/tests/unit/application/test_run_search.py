"""RunSearch: las 8 etapas del pipeline con piezas en memoria (sin red, base ni gasto)."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.audit import Actor
from app.application.ports.extraction import Extraction
from app.application.ports.llm import (
    ClassificationError,
    EnrichmentError,
    EnrichmentRequest,
    EnrichmentResult,
)
from app.application.ports.providers import ProviderResponse
from app.application.ports.search_store import (
    NewSearch,
    ProcessingErrorRecord,
    SearchClosing,
    SearchConcept,
    SearchResultRow,
    StoredArticle,
    StoredSearch,
)
from app.application.use_cases.classify import ClassifyReport
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionLimits
from app.application.use_cases.extraction import ExtractTexts
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.run_search import (
    PipelineLimits,
    RunSearch,
    SearchNotFoundError,
    plan_queries,
)
from app.domain.articles import RawArticle
from app.domain.dedupe import DedupedArticle, KnownArticle
from app.domain.enrichment import ConceptJudgement, Enrichment, LLMUsage
from app.domain.errors import ProviderUnavailableError
from app.domain.extraction import ExtractionStatus, ProcessingText
from app.domain.geocoding import Mention, MentionRole, Resolution
from app.domain.names import normalize_name
from app.domain.queries import PlannedQuery, Provider, QueryPlace
from app.domain.schedule import RunWindow
from app.domain.search import SearchStatus, Stage
from tests.unit import fake_gazetteer as cat
from tests.unit.application.test_execute_queries import MEXICO as MEXICO_FILTER
from tests.unit.application.test_execute_queries import WEEK, FakeCache, FakeLog
from tests.unit.fake_regions import ALL as ALL_REGIONS
from tests.unit.fake_regions import CDMX as CDMX_REGION
from tests.unit.fake_regions import FakeRegionRepository

pytestmark = pytest.mark.anyio

PUBLISHED = datetime(2026, 10, 15, 12, tzinfo=UTC)
EXTORSION = SearchConcept(3, "Extorsión", "Cobro de piso", ("extorsión", "cobro de piso"))
IZTA_TITLE = "Detienen a extorsionadores en Iztapalapa"
IZTA_BODY = (
    "Policías de la Ciudad de México detuvieron a dos extorsionadores en Iztapalapa que "
    "cobraban piso a comerciantes del mercado. "
) * 4
MADRID_TITLE = "Desmantelan red de extorsión en Madrid"


def raw(provider: Provider, rank: int, url: str, title: str) -> RawArticle:
    return RawArticle.create(
        provider=provider, provider_rank=rank, url=url, title=title, published_at=PUBLISHED
    )


IZTA_SEARCHAPI = raw(Provider.SEARCHAPI, 1, "https://www.milenio.com/izta?utm_source=x", IZTA_TITLE)
IZTA_LOCAL = raw(Provider.LOCAL_INDEX, 3, "https://milenio.com/izta", IZTA_TITLE)
MADRID = raw(Provider.SEARCHAPI, 2, "https://elpais.com/madrid", MADRID_TITLE)


class Source:
    """Proveedor falso que devuelve notas fijas."""

    def __init__(
        self,
        provider: Provider,
        articles: Sequence[RawArticle],
        *,
        cost: int = 0,
        configured: bool = True,
        error: Exception | None = None,
    ) -> None:
        self._provider = provider
        self.articles = tuple(articles)
        self.cost = cost
        self.configured = configured
        self.error = error
        self.queries: list[PlannedQuery] = []

    @property
    def provider(self) -> Provider:
        return self._provider

    def is_configured(self) -> bool:
        return self.configured

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        return {"q": query.text}

    def estimate_cost(self, query: PlannedQuery) -> int:
        return self.cost

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        self.queries.append(query)
        if self.error:
            raise self.error
        return ProviderResponse(self.articles, 200, {"q": query.text}, "{}")


class Searches:
    """``SearchStorePort`` en memoria."""

    def __init__(self, search: StoredSearch | None) -> None:
        self.search = search
        self.started = False
        self.progress: list[Mapping[str, object]] = []
        self.errors: list[ProcessingErrorRecord] = []
        self.closing: SearchClosing | None = None
        self.actor: Actor | None = None

    async def create(self, search: NewSearch) -> UUID:
        raise NotImplementedError

    async def load(self, search_id: UUID) -> StoredSearch | None:
        return self.search

    async def start(self, search_id: UUID) -> None:
        self.started = True

    async def set_progress(self, search_id: UUID, progress: Mapping[str, object]) -> None:
        self.progress.append(progress)

    async def record_error(self, error: ProcessingErrorRecord) -> None:
        self.errors.append(error)

    async def finish(self, search_id: UUID, closing: SearchClosing, actor: Actor) -> None:
        self.closing = closing
        self.actor = actor

    @property
    def stages(self) -> list[object]:
        stages: list[object] = []
        for p in self.progress:
            if not stages or stages[-1] != p["stage"]:
                stages.append(p["stage"])
        return stages


class Articles:
    """``ArticleStorePort`` en memoria."""

    def __init__(
        self,
        known: Mapping[str, StoredArticle] | None = None,
        *,
        stored_titles: Sequence[KnownArticle] = (),
        by_id: Mapping[int, StoredArticle] | None = None,
    ) -> None:
        self.known = dict(known or {})
        self.stored_titles = list(stored_titles)
        self.by_id = dict(by_id or {})
        self.ids: dict[str, int] = {}
        self.texts: dict[int, ProcessingText] = {}
        self.enriched: dict[int, tuple[EnrichmentResult, list[Resolution]]] = {}
        self.failed: list[int] = []
        self.rows: list[SearchResultRow] = []

    async def known_like(self, articles: Sequence[DedupedArticle]) -> list[list[KnownArticle]]:
        return [list(self.stored_titles) for _ in articles]

    async def upsert(self, articles: Sequence[DedupedArticle]) -> list[StoredArticle]:
        out = []
        for a in articles:
            if a.known_id is not None:
                out.append(self.by_id.get(a.known_id, StoredArticle(a.known_id)))
                continue
            if a.url_canonical in self.known:
                out.append(self.known[a.url_canonical])
                continue
            article_id = self.ids.setdefault(a.url_canonical, len(self.ids) + 100)
            out.append(StoredArticle(article_id))
        return out

    async def save_text(self, article_id: int, text: ProcessingText) -> None:
        self.texts[article_id] = text

    async def save_enrichment(
        self, article_id: int, result: EnrichmentResult, resolutions: Sequence[Resolution]
    ) -> None:
        self.enriched[article_id] = (result, list(resolutions))

    async def mark_enrichment_failed(self, article_id: int) -> None:
        self.failed.append(article_id)

    async def link_results(self, search_id: UUID, rows: Sequence[SearchResultRow]) -> None:
        self.rows.extend(rows)


class Extractor:
    def __init__(self, bodies: Mapping[str, str]) -> None:
        self.bodies = bodies
        self.urls: list[str] = []

    async def extract(self, url: str) -> Extraction:
        self.urls.append(url)
        body = self.bodies.get(url)
        return Extraction(body) if body else Extraction(None, "HTTP 403")


def enrichment(*mentions: Mention, relevant: bool = True) -> Enrichment:
    return Enrichment(
        (ConceptJudgement(3, relevant, 0.9 if relevant else 0.1, "Habla de extorsión."),),
        "Resumen propio.",
        "extorsión",
        date(2026, 10, 15),
        mentions,
    )


class LLM:
    def __init__(self, replies: Mapping[str, Enrichment | Exception]) -> None:
        self.replies = replies
        self.requests: list[EnrichmentRequest] = []

    @property
    def model(self) -> str:
        return "modelo-de-prueba"

    @property
    def prompt_version(self) -> str:
        return "enrich_v1"

    async def aclose(self) -> None:
        return None

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        self.requests.append(request)
        reply = self.replies[request.title]
        if isinstance(reply, Exception):
            raise reply
        # Como el adaptador real: un juicio por cada concepto que se le pidió.
        judged = reply.concepts[0]
        concepts = tuple(replace(judged, concept_id=c.concept_id) for c in request.concepts)
        return EnrichmentResult(
            replace(reply, concepts=concepts), LLMUsage(1000, 100), self.model, self.prompt_version
        )


IZTA_MENTION = Mention("Iztapalapa", MentionRole.EVENT, state_hint="Ciudad de México")
MADRID_MENTION = Mention("Madrid", MentionRole.EVENT, country="España")
DEFAULT_REPLIES: dict[str, Enrichment | Exception] = {
    IZTA_TITLE: enrichment(IZTA_MENTION),
    MADRID_TITLE: enrichment(MADRID_MENTION),
}


def stored_search(*concepts: SearchConcept) -> StoredSearch:
    return StoredSearch(
        search_id=uuid4(),
        user_id="benji",
        region_id=CDMX_REGION.id,
        region_code="09",
        date_from=date(2026, 10, 10),
        date_to=date(2026, 10, 16),
        status=SearchStatus.PENDING,
        concepts=concepts or (EXTORSION,),
    )


def pipeline(
    *,
    sources: Sequence[Source] | None = None,
    search: StoredSearch | None = None,
    articles: Articles | None = None,
    replies: Mapping[str, Enrichment | Exception] | None = None,
    max_llm_articles: int = 150,
    region_missing: bool = False,
    stories: Any = None,
    classifier: Any = None,
) -> tuple[RunSearch, Searches, Articles, LLM, Extractor]:
    sources = (
        sources
        if sources is not None
        else [
            Source(Provider.SEARCHAPI, [IZTA_SEARCHAPI, MADRID], cost=1),
            Source(Provider.LOCAL_INDEX, [IZTA_LOCAL]),
        ]
    )
    providers = {s.provider: s for s in sources}
    searches = Searches(search or stored_search())
    articles = articles or Articles()
    llm = LLM(replies if replies is not None else DEFAULT_REPLIES)
    extractor = Extractor({IZTA_SEARCHAPI.url: IZTA_BODY})
    regions = FakeRegionRepository(() if region_missing else ALL_REGIONS)
    executor = ExecuteQueries(
        providers,
        FakeCache(),
        FakeLog(),
        ExecutionLimits(10, 0, {Provider.SEARCHAPI: 100}),
    )
    use_case = RunSearch(
        searches=searches,
        articles=articles,
        regions=regions,
        gazetteer=cat.FakeGazetteer(),
        providers=providers,
        executor=executor,
        extractor=ExtractTexts(extractor, 2),
        llm=llm,
        geocoder=GeocodeMentions(cat.FakeGazetteer()),
        similarity=lambda a, b: 1.0 if a == b else 0.0,
        limits=PipelineLimits(max_llm_articles, 2, 0.10, 0.50),
        stories=stories,
        classifier=classifier,
    )
    return use_case, searches, articles, llm, extractor


async def test_busqueda_completa_de_punta_a_punta() -> None:
    use_case, searches, articles, llm, extractor = pipeline()

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.COMPLETED
    assert (report.articles, report.enriched, report.fallback) == (2, 2, 1)
    assert (report.in_region, report.out_of_region, report.unlocated) == (1, 1, 0)
    assert report.credits_used == 1
    assert report.llm_usage == LLMUsage(2000, 200)
    assert report.llm_cost_usd == pytest.approx(0.0003)
    # La misma nota de dos proveedores es una sola, con los dos registrados.
    izta_id = articles.ids["https://milenio.com/izta"]
    assert sorted(
        (r.provider, r.provider_rank) for r in articles.rows if r.article_id == izta_id
    ) == [
        ("indice_local", 3),
        ("searchapi", 1),
    ]
    assert {r.article_id: r.in_region for r in articles.rows}[izta_id] is True
    # La página se lee con la URL original del primer proveedor.
    assert sorted(extractor.urls) == sorted([IZTA_SEARCHAPI.url, MADRID.url])
    assert articles.texts[izta_id].status is ExtractionStatus.OK
    _result, resolutions = articles.enriched[izta_id]
    assert [(r.place, r.is_primary) for r in resolutions] == [(cat.IZTAPALAPA, True)]
    assert len(llm.requests) == 2
    assert searches.started
    assert searches.stages == [
        "query",
        "dedupe",
        "extract",
        "enrich",
        "geocode",
        "filter",
        "close",
    ]
    closing = searches.closing
    assert closing is not None
    assert closing.status is SearchStatus.COMPLETED
    assert closing.results_count == 2
    assert [q["provider"] for q in closing.queries_executed] == ["searchapi", "indice_local"]
    assert searches.actor == Actor("benji")
    assert searches.errors == []


async def test_nota_ya_enriquecida_se_reutiliza_sin_bajarla_ni_pagarla() -> None:
    known = {
        "https://milenio.com/izta": StoredArticle(7, "enrich_v1", frozenset({3}), "09007"),
    }
    use_case, _s, articles, llm, extractor = pipeline(articles=Articles(known))

    report = await use_case.run(uuid4())

    assert report.reused == 1
    assert [r.title for r in llm.requests] == [MADRID_TITLE]
    assert IZTA_SEARCHAPI.url not in extractor.urls
    assert {r.article_id: r.in_region for r in articles.rows}[7] is True


async def test_misma_nota_guardada_con_otro_link_se_reutiliza() -> None:
    # Nivel 2 de duplicados (ADR-0025): la nota ya estaba guardada con el link
    # de Google News; llega con el del medio y se usa la misma, con su IA.
    google = KnownArticle(
        7, "https://news.google.com/rss/articles/CBMi", normalize_name(IZTA_TITLE), PUBLISHED
    )
    articles = Articles(
        stored_titles=[google],
        by_id={7: StoredArticle(7, "enrich_v1", frozenset({3}), "09007")},
    )
    use_case, _s, _a, llm, _e = pipeline(articles=articles)

    report = await use_case.run(uuid4())

    assert report.reused == 1
    assert [r.title for r in llm.requests] == [MADRID_TITLE]
    assert 7 in {r.article_id for r in articles.rows}


@pytest.mark.parametrize(
    ("stored", "why"),
    [
        (StoredArticle(7, "enrich_v0", frozenset({3}), "09007"), "otra versión del prompt"),
        (StoredArticle(7, "enrich_v1", frozenset({9}), "09007"), "otro concepto"),
        (StoredArticle(7, None, frozenset(), None), "sin enriquecer"),
    ],
)
async def test_nota_guardada_que_no_sirve_se_vuelve_a_enriquecer(
    stored: StoredArticle, why: str
) -> None:
    use_case, _s, _a, llm, _e = pipeline(articles=Articles({"https://milenio.com/izta": stored}))

    report = await use_case.run(uuid4())

    assert report.reused == 0, why
    assert len(llm.requests) == 2


async def test_el_tope_por_busqueda_deja_notas_sin_enriquecer() -> None:
    use_case, searches, _a, llm, _e = pipeline(max_llm_articles=1)

    report = await use_case.run(uuid4())

    assert len(llm.requests) == 1
    assert report.skipped_by_cap == 1
    # Sin ubicación porque no se enriqueció: queda en "Sin ubicación".
    assert report.unlocated == 1
    assert report.status is SearchStatus.COMPLETED
    assert searches.closing is not None
    assert searches.closing.progress["skipped_by_cap"] == 1


async def test_si_la_ia_falla_en_mas_de_la_mitad_la_busqueda_es_parcial() -> None:
    replies: dict[str, Enrichment | Exception] = {
        IZTA_TITLE: EnrichmentError("JSON inválido", LLMUsage(500, 20)),
        MADRID_TITLE: ProviderUnavailableError("OpenAI no respondió.", provider="openai"),
    }
    use_case, searches, articles, _l, _e = pipeline(replies=replies)

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.PARTIAL
    assert report.enrich_failed == 2
    # Lo gastado en intentos fallidos también cuenta.
    assert report.llm_usage == LLMUsage(500, 20)
    assert sorted(articles.failed) == sorted(articles.ids.values())
    assert [e.stage.value for e in searches.errors] == ["enrich", "enrich"]
    assert {e.error_type for e in searches.errors} == {
        "EnrichmentError",
        "ProviderUnavailableError",
    }
    assert report.error_summary is not None
    assert "La IA falló en 2 de 2 notas" in report.error_summary


async def test_una_falla_de_la_ia_no_basta_para_parcial() -> None:
    replies: dict[str, Enrichment | Exception] = {
        **DEFAULT_REPLIES,
        MADRID_TITLE: EnrichmentError("JSON inválido", LLMUsage(0, 0)),
    }
    use_case, _s, _a, _l, _e = pipeline(replies=replies)

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.COMPLETED
    assert report.enrich_failed == 1


async def test_si_ningun_proveedor_responde_la_busqueda_falla_sin_procesar() -> None:
    down = ProviderUnavailableError("SearchApi no respondió.", provider="searchapi")
    sources = [Source(Provider.SEARCHAPI, [], cost=1, error=down)]
    use_case, _s, articles, llm, _e = pipeline(sources=sources)

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.FAILED
    assert report.articles == 0
    assert llm.requests == []
    assert articles.rows == []
    assert report.error_summary == "searchapi: SearchApi no respondió."


async def test_un_proveedor_caido_deja_la_busqueda_parcial_con_lo_demas() -> None:
    down = ProviderUnavailableError("SearchApi no respondió.", provider="searchapi")
    sources = [
        Source(Provider.SEARCHAPI, [], cost=1, error=down),
        Source(Provider.LOCAL_INDEX, [IZTA_LOCAL]),
    ]
    use_case, _s, _a, _l, _e = pipeline(sources=sources)

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.PARTIAL
    assert (report.articles, report.credits_used) == (1, 0)


async def test_proveedor_sin_configurar_no_se_planea() -> None:
    sources = [
        Source(Provider.SEARCHAPI, [MADRID], cost=1, configured=False),
        Source(Provider.LOCAL_INDEX, [IZTA_LOCAL]),
    ]
    use_case, searches, _a, _l, _e = pipeline(sources=sources)

    report = await use_case.run(uuid4())

    assert sources[0].queries == []
    assert report.status is SearchStatus.COMPLETED
    assert searches.closing is not None
    assert [q["provider"] for q in searches.closing.queries_executed] == ["indice_local"]


async def test_concepto_sin_palabras_falla_al_planear() -> None:
    empty = SearchConcept(4, "Vacío", "", ())
    use_case, searches, _a, _l, _e = pipeline(search=stored_search(empty))

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.FAILED
    assert [(e.stage.value, e.error_type) for e in searches.errors] == [
        ("plan", "ConceptValidationError")
    ]


async def test_region_que_no_existe_falla_al_planear() -> None:
    use_case, _s, _a, _l, _e = pipeline(region_missing=True)

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.FAILED
    assert "09" in (report.error_summary or "")


async def test_busqueda_inexistente() -> None:
    use_case, searches, _a, _l, _e = pipeline()
    searches.search = None

    with pytest.raises(SearchNotFoundError):
        await use_case.run(uuid4())


async def test_el_avance_se_actualiza_durante_la_ia() -> None:
    many = [
        raw(Provider.LOCAL_INDEX, i, f"https://milenio.com/n{i}", f"Nota número {i}")
        for i in range(1, 13)
    ]
    replies: dict[str, Enrichment | Exception] = {a.title: enrichment() for a in many}
    use_case, searches, _a, _l, _e = pipeline(
        sources=[Source(Provider.LOCAL_INDEX, many)], replies=replies
    )

    report = await use_case.run(uuid4())

    assert report.enriched == 12
    assert any(p["stage"] == "enrich" and p.get("enriched") == 10 for p in searches.progress)


def test_plan_de_varios_conceptos() -> None:

    otro = SearchConcept(5, "Secuestro", "", ("secuestro",))
    queries = plan_queries(
        [EXTORSION, otro],
        QueryPlace(("Iztapalapa",), (), MEXICO_FILTER),
        WEEK,
        [Provider.LOCAL_INDEX],
    )

    assert [q.keywords for q in queries] == [("extorsión", "cobro de piso"), ("secuestro",)]


class Stories:
    """``GroupStories`` falso: anota qué notas recibió o falla."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.received: list[list[int]] = []

    async def run(self, article_ids: Sequence[int]) -> int:
        self.received.append(list(article_ids))
        if self.error:
            raise self.error
        return len(article_ids)


async def test_al_cerrar_agrupa_en_historias_las_notas_encontradas() -> None:
    stories = Stories()
    use_case, _s, articles, _l, _e = pipeline(stories=stories)

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.COMPLETED
    assert sorted(stories.received[0]) == sorted({r.article_id for r in articles.rows})


async def test_si_agrupar_falla_la_busqueda_no_se_cae() -> None:
    use_case, searches, _a, _l, _e = pipeline(stories=Stories(RuntimeError("base caída")))

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.COMPLETED
    assert [(e.stage, e.message) for e in searches.errors] == [
        (Stage.CLOSE, "Historias: base caída")
    ]


@pytest.mark.parametrize(
    ("providers", "queried"),
    [
        # Switches (F12.2): solo las fuentes que eligió el analista.
        ((Provider.LOCAL_INDEX,), {Provider.LOCAL_INDEX}),
        # Búsqueda de antes de F12.2 (sin fuentes guardadas): todas, como entonces.
        ((), {Provider.SEARCHAPI, Provider.LOCAL_INDEX}),
    ],
)
async def test_corre_con_las_fuentes_de_la_busqueda(
    providers: tuple[Provider, ...], queried: set[Provider]
) -> None:
    sources = [
        Source(Provider.SEARCHAPI, [IZTA_SEARCHAPI, MADRID], cost=1),
        Source(Provider.LOCAL_INDEX, [IZTA_LOCAL]),
    ]
    search = replace(stored_search(), providers=providers)
    use_case, _s, _a, _l, _e = pipeline(sources=sources, search=search)

    await use_case.run(search.search_id)

    assert {s.provider for s in sources if s.queries} == queried


class Classifier:
    """``ClassifyArticles`` falso: cuesta tokens o falla."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.received: list[list[int]] = []

    async def run(self, article_ids: Sequence[int]) -> Any:
        self.received.append(list(article_ids))
        if self.error:
            raise self.error
        return ClassifyReport(classified=len(article_ids), usage=LLMUsage(1000, 100))


async def test_al_cerrar_clasifica_y_suma_su_costo_a_la_busqueda() -> None:
    use_case, searches, _a, _l, _e = pipeline(classifier=Classifier())
    without, _s2, _a2, _l2, _e2 = pipeline()

    report = await use_case.run(uuid4())
    base = await without.run(uuid4())

    assert report.status is SearchStatus.COMPLETED
    # 1000 tokens de entrada y 100 de salida a 0.10 y 0.50 USD por millón.
    assert report.llm_usage.tokens_in == base.llm_usage.tokens_in + 1000
    assert searches.closing is not None
    assert searches.closing.llm_usage.tokens_out == base.llm_usage.tokens_out + 100


async def test_si_clasificar_falla_la_busqueda_sigue_y_cuenta_lo_gastado() -> None:
    failing = Classifier(ClassificationError("JSON inválido", LLMUsage(300, 5)))
    use_case, searches, _a, _l, _e = pipeline(classifier=failing)

    report = await use_case.run(uuid4())

    assert report.status is SearchStatus.COMPLETED
    assert any(e.message.startswith("Clasificación:") for e in searches.errors)


async def test_la_corrida_automatica_solo_toma_lo_publicado_en_sus_horas() -> None:
    # Benji, 28/10/2026: cada corrida, solo lo publicado desde la anterior.
    # MADRID se publicó una hora antes de que empezara la ventana.
    early = replace(MADRID, published_at=PUBLISHED - timedelta(hours=9))
    window = RunWindow(PUBLISHED - timedelta(hours=8), PUBLISHED + timedelta(hours=1))
    search = replace(stored_search(), time_window=window)
    use_case, _searches, articles, llm, _e = pipeline(
        sources=[
            Source(Provider.SEARCHAPI, [IZTA_SEARCHAPI, early], cost=1),
            Source(Provider.LOCAL_INDEX, [IZTA_LOCAL]),
        ],
        search=search,
    )

    report = await use_case.run(uuid4())

    # Lo de fuera ni se guarda ni se paga a la IA.
    assert report.articles == 1
    assert "https://elpais.com/madrid" not in articles.ids
    assert report.enriched == 1
    assert len(llm.requests) == 1


async def test_la_corrida_no_trae_una_nota_vieja_que_llega_con_fecha_nueva() -> None:
    # Corrida de las 15:00 del 28/10/2026: el índice local mandó de nuevo 6
    # notas de la madrugada con una fecha dentro de la ventana. Pasaban el
    # filtro y, al reconocerlas como ya guardadas, quedaban con su fecha real
    # (03:30–06:51), fuera de las horas y repetidas de la corrida anterior.
    window = RunWindow(PUBLISHED - timedelta(hours=8), PUBLISHED + timedelta(hours=1))
    search = replace(stored_search(), time_window=window)
    old = StoredArticle(55, "enrich_v1", frozenset({3}), "09007", PUBLISHED - timedelta(hours=9))
    articles = Articles(known={"https://elpais.com/madrid": old})
    use_case, _searches, articles, llm, _e = pipeline(articles=articles, search=search)

    report = await use_case.run(uuid4())

    assert 55 not in {r.article_id for r in articles.rows}
    assert report.articles == 1
    assert [r.title for r in llm.requests] == [IZTA_TITLE]


async def test_la_corrida_deja_fuera_lo_que_paso_antes_de_su_periodo() -> None:
    # Benji, 28/10/2026: nada de otros días. El cateo de ayer publicado hoy
    # sale; la sentencia de hoy por un delito viejo se queda (la IA da la fecha
    # de lo que informa la nota, enrich_v3).
    window = RunWindow(PUBLISHED - timedelta(hours=8), PUBLISHED + timedelta(hours=1))
    search = replace(stored_search(), time_window=window)
    # La ventana empieza a las 22:00 del 14/10 en la CDMX: lo del 13/10 es de antes.
    before_window = (PUBLISHED - timedelta(days=2)).date()
    replies: dict[str, Enrichment | Exception] = {
        IZTA_TITLE: enrichment(IZTA_MENTION),
        MADRID_TITLE: replace(enrichment(MADRID_MENTION), event_date=before_window),
    }
    use_case, _searches, articles, _llm, _e = pipeline(search=search, replies=replies)

    report = await use_case.run(uuid4())

    linked = {r.article_id for r in articles.rows}
    assert articles.ids["https://elpais.com/madrid"] not in linked
    assert report.articles == 1
    assert len(linked) == 1


async def test_con_subdivision_la_palabra_del_tema_va_en_el_titulo_o_el_resumen() -> None:
    # Benji, 03/11/2026: en «FGR · Homicidio» no basta que la palabra esté
    # perdida en el cuerpo. MADRID no dice «Iztapalapa» arriba: ni se guarda
    # ni se paga a la IA.
    search = stored_search(replace(EXTORSION, topic_terms=("Iztapalapa",), category_ids=(5,)))
    use_case, searches, articles, llm, _e = pipeline(search=search)

    report = await use_case.run(uuid4())

    assert report.articles == 1
    assert "https://elpais.com/madrid" not in articles.ids
    assert [r.title for r in llm.requests] == [IZTA_TITLE]
    assert searches.progress[-1]["off_topic"] == 1


async def test_lo_que_trae_otra_consulta_sin_subdivision_se_queda() -> None:
    # MADRID llega por las dos consultas: la del tema «Secuestro», que no
    # lleva subdivisión, la deja pasar aunque la de la FGR no.
    fgr = replace(EXTORSION, topic_terms=("Iztapalapa",), category_ids=(5,))
    secuestro = SearchConcept(17, "Secuestro", "", ("secuestro",))
    use_case, _searches, articles, _llm, _e = pipeline(search=stored_search(fgr, secuestro))

    report = await use_case.run(uuid4())

    assert report.articles == 2
    assert "https://elpais.com/madrid" in articles.ids


async def test_sin_subdivision_no_cambia_nada() -> None:
    use_case, searches, _articles, _llm, _e = pipeline()

    report = await use_case.run(uuid4())

    assert report.articles == 2
    assert "off_topic" not in searches.progress[-1]
