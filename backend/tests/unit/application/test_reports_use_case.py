"""Armar el reporte y exportar notas, con puertos en memoria: sin base ni IA (§15)."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.application.audit import Actor
from app.application.pagination import TimeCursor
from app.application.ports.llm import SummaryError, SummaryRequest, SummaryResult
from app.application.ports.reports import (
    MapPoint,
    ProviderUsage,
    StoredSummary,
    SubregionCount,
)
from app.application.ports.search_reads import (
    ArticleDetail,
    ArticleFilters,
    ArticleItem,
    CategoryCount,
    ConceptRef,
    LocationView,
    PreviousRun,
    RegionPoint,
    SearchDetail,
)
from app.application.use_cases import reports
from app.application.use_cases.reports import (
    FAILED_NOTICE,
    NO_LLM_NOTICE,
    NO_NOTES_NOTICE,
    BuildReport,
    ExportSearch,
    LLMPrices,
    ReportFormat,
)
from app.application.use_cases.run_search import SearchNotFoundError
from app.domain.aggregates import AggregateLevel, NoteLocation
from app.domain.enrichment import LLMUsage
from app.domain.errors import ProviderUnavailableError, RegionNotFoundError, SearchNotFinishedError
from app.domain.geocoding import Precision
from app.domain.region import Region, RegionLevel
from app.domain.search import SearchStatus, SearchTrigger
from tests.unit.fake_regions import ALL, CDMX, MEXICO, FakeRegionRepository, make_region

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 17, 20, tzinfo=UTC)
ACTOR = Actor("benji", "127.0.0.1")
PRICES = LLMPrices("openai", 0.10, 0.50)


def search(status: SearchStatus = SearchStatus.COMPLETED) -> SearchDetail:
    return SearchDetail(
        search_id=uuid4(),
        user_id="benji",
        status=status,
        region_id=CDMX.id,
        region_code=CDMX.code,
        region_name=CDMX.name,
        date_from=date(2026, 10, 10),
        date_to=date(2026, 10, 17),
        concepts=(ConceptRef(3, "Extorsión"),),
        progress={"stage": "close"},
        queries_planned=2,
        credits_estimated=1,
        credits_used=1,
        llm_usage=LLMUsage(5000, 900),
        llm_cost_usd=0.0013,
        results_count=3,
        error_summary=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )


def place(code: str, precision: str, name: str) -> LocationView:
    return LocationView("x", "event", precision, 0.9, True, 1, code, name, -99.1, 19.4)


def item(
    article_id: int, summary: str | None = "Resumen.", primary: LocationView | None = None
) -> ArticleItem:
    return ArticleItem(
        article_id,
        f"Nota {article_id} de Peñón",
        "El Universal",
        "eluniversal.com.mx",
        f"https://medio.mx/{article_id}",
        datetime(2026, 10, 16, tzinfo=UTC),
        summary,
        "extorsión",
        None,
        "ok",
        "ok",
        (),
        primary,
        True,
        ("searchapi",),
    )


IZTAPALAPA_NOTE = item(1, primary=place("09007", "municipality", "Alcaldía Iztapalapa"))
STATE_NOTE = item(2, primary=place("09", "state", "Ciudad de México"))
UNLOCATED_NOTE = item(3, summary=None)


class Reader:
    def __init__(self, row: SearchDetail) -> None:
        self.row = row

    async def search_detail(self, search_id: UUID) -> SearchDetail | None:
        return self.row if search_id == self.row.search_id else None

    async def history(
        self, user_id: str, after: TimeCursor | None, limit: int
    ) -> list[SearchDetail]:
        return []


class Articles:
    def __init__(self, rows: Sequence[ArticleItem]) -> None:
        self.rows = list(rows)
        self.pages = 0

    async def search_articles(
        self, search_id: UUID, filters: ArticleFilters, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        assert filters == ArticleFilters()  # solo las relevantes
        self.pages += 1
        start = 0 if after is None else int(after.id)
        return self.rows[start : start + limit]

    async def article_detail(self, article_id: int) -> ArticleDetail | None:
        return None

    async def note_locations(self, search_id: UUID, filters: ArticleFilters) -> list[NoteLocation]:
        return [
            NoteLocation("09007", "MEX", Precision.MUNICIPALITY),  # Iztapalapa
            NoteLocation("09007", "MEX", Precision.LOCALITY),
            NoteLocation("09015", "MEX", Precision.MUNICIPALITY),  # Cuauhtémoc
            NoteLocation("09", "MEX", Precision.STATE),  # solo la CDMX
            NoteLocation("16", "MEX", Precision.STATE),  # solo "Michoacán": fuera
            NoteLocation("14039", "MEX", Precision.MUNICIPALITY),  # Guadalajara: fuera
            NoteLocation("FRA", "FRA", Precision.COUNTRY),  # París: fuera
            NoteLocation(None, None, Precision.UNKNOWN),
        ]

    async def category_counts(
        self, search_id: UUID, filters: ArticleFilters
    ) -> list[CategoryCount]:
        # Sin categorías en estas pruebas (F12.4 se prueba aparte).
        return []

    async def regions_by_code(self, codes: Sequence[str]) -> list[RegionPoint]:
        names = {"09007": "Iztapalapa", "09015": "Cuauhtémoc"}
        return [RegionPoint(1, c, names[c], -99.1, 19.4) for c in codes if c in names]


class Store:
    def __init__(self, stored: StoredSummary | None = None) -> None:
        self.stored = stored
        self.saved: list[StoredSummary] = []
        self.generated: list[tuple[UUID, str, Actor]] = []

    async def summary(self, search_id: UUID) -> StoredSummary | None:
        return self.stored

    async def save_summary(self, search_id: UUID, summary: StoredSummary, actor: Actor) -> None:
        self.saved.append(summary)

    async def provider_usage(self, search_id: UUID) -> list[ProviderUsage]:
        return [ProviderUsage("searchapi", 1, 12, 1, 0, 0)]

    async def record_generated(self, search_id: UUID, report_format: str, actor: Actor) -> None:
        self.generated.append((search_id, report_format, actor))


class Map:
    def __init__(self) -> None:
        self.calls: list[tuple[Region, AggregateLevel, list[SubregionCount], list[MapPoint]]] = []

    async def render(
        self,
        region: Region,
        level: AggregateLevel,
        counts: Sequence[SubregionCount],
        points: Sequence[MapPoint],
    ) -> str:
        self.calls.append((region, level, list(counts), list(points)))
        return "<svg/>"


class Summarizer:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.requests: list[SummaryRequest] = []

    @property
    def model(self) -> str:
        return "gpt-6-luna"

    @property
    def summary_prompt_version(self) -> str:
        return "summary_v1"

    async def aclose(self) -> None:
        return None

    async def summarize(self, request: SummaryRequest) -> SummaryResult:
        self.requests.append(request)
        if self.error:
            raise self.error
        return SummaryResult("Predomina el cobro de piso.", LLMUsage(2000, 300), "gpt-6-luna", "s1")


class PreviousRuns:
    """Corridas anteriores en memoria; anota por cuáles le preguntaron."""

    def __init__(self, found: PreviousRun | None) -> None:
        self.found = found
        self.asked: list[UUID] = []

    async def previous_automatic_run(self, search_id: UUID) -> PreviousRun | None:
        self.asked.append(search_id)
        return self.found


def build(
    row: SearchDetail,
    *,
    rows: Sequence[ArticleItem] = (IZTAPALAPA_NOTE, STATE_NOTE, UNLOCATED_NOTE),
    store: Store | None = None,
    summarizer: Summarizer | None = None,
    prices: LLMPrices | None = PRICES,
    static_map: Map | None = None,
    regions: FakeRegionRepository | None = None,
    previous_runs: PreviousRuns | None = None,
) -> BuildReport:
    return BuildReport(
        searches=Reader(row),
        articles=Articles(rows),
        regions=regions or FakeRegionRepository(),
        store=store or Store(),
        static_map=static_map or Map(),
        summarizer=summarizer,
        prices=prices,
        clock=lambda: NOW,
        previous_runs=previous_runs,
    )


async def test_la_corrida_automatica_trae_la_anterior_para_separar_lo_nuevo() -> None:
    row = replace(search(), trigger=SearchTrigger.AUTOMATIC, scheduled_for=NOW)
    previous = PreviousRun(uuid4(), NOW, frozenset({1}))
    runs = PreviousRuns(previous)

    data = await build(row, previous_runs=runs).execute(row.search_id, ReportFormat.PDF, ACTOR)

    assert data.previous_run == previous
    assert runs.asked == [row.search_id]


async def test_una_busqueda_manual_no_se_compara_con_ninguna_corrida() -> None:
    row = search()
    runs = PreviousRuns(PreviousRun(uuid4(), NOW, frozenset({1})))

    data = await build(row, previous_runs=runs).execute(row.search_id, ReportFormat.PDF, ACTOR)

    assert data.previous_run is None
    assert runs.asked == []


async def test_reporte_completo_con_resumen_nuevo_que_se_guarda() -> None:
    row = search()
    store, summarizer, static_map = Store(), Summarizer(), Map()

    data = await build(row, store=store, summarizer=summarizer, static_map=static_map).execute(
        row.search_id, ReportFormat.PDF, ACTOR
    )

    assert data.breadcrumb == "México › Ciudad de México"
    assert data.level is AggregateLevel.MUNICIPALITY
    # Solo las alcaldías de la CDMX; Guadalajara y París cuentan como de fuera.
    assert data.counts == (
        SubregionCount("09007", "Iztapalapa", 2),
        SubregionCount("09015", "Cuauhtémoc", 1),
    )
    # "Michoacán" a secas es de fuera, no "menos precisa" (no está en la CDMX).
    assert (data.outside, data.coarser, data.unlocated) == (3, 1, 1)
    assert [a.article_id for a in data.articles] == [1, 2, 3]
    assert (data.summary, data.summary_model, data.summary_notice) == (
        "Predomina el cobro de piso.",
        "gpt-6-luna",
        None,
    )
    assert (data.map_svg, data.generated_at, data.generated_by) == ("<svg/>", NOW, "benji")
    assert data.providers == (ProviderUsage("searchapi", 1, 12, 1, 0, 0),)
    # A la IA solo van las notas con resumen: título, lugar, fecha y resumen.
    [request] = summarizer.requests
    assert (request.concepts, request.region) == (["Extorsión"], "México › Ciudad de México")
    assert [(n.title, n.place) for n in request.notes] == [
        ("Nota 1 de Peñón", "Alcaldía Iztapalapa"),
        ("Nota 2 de Peñón", "Ciudad de México"),
    ]
    [saved] = store.saved
    assert (saved.provider, saved.usage) == ("openai", LLMUsage(2000, 300))
    assert saved.cost_usd == pytest.approx(0.00035)
    # El mapa recibe los conteos y los puntos; lo de solo estado va punteado.
    _region, level, counts, points = static_map.calls[0]
    assert (level, counts) == (AggregateLevel.MUNICIPALITY, list(data.counts))
    assert [p.coarse for p in points] == [False, True]
    assert store.generated == [(row.search_id, "pdf", ACTOR)]


async def test_el_resumen_guardado_no_se_vuelve_a_pagar() -> None:
    row = search()
    stored = StoredSummary("Ya escrito.", "openai", "gpt-6-luna", "summary_v1", LLMUsage(1, 1), 0)
    summarizer = Summarizer()

    data = await build(row, store=Store(stored), summarizer=summarizer).execute(
        row.search_id, ReportFormat.HTML, ACTOR
    )

    assert data.summary == "Ya escrito."
    assert summarizer.requests == []


@pytest.mark.parametrize(
    ("summarizer", "prices", "rows", "notice"),
    [
        (None, None, (IZTAPALAPA_NOTE,), NO_LLM_NOTICE),
        (Summarizer(), PRICES, (UNLOCATED_NOTE,), NO_NOTES_NOTICE),
        (Summarizer(SummaryError("mal", LLMUsage(5, 5))), PRICES, (STATE_NOTE,), FAILED_NOTICE),
        (
            Summarizer(ProviderUnavailableError("caída", provider="openai")),
            PRICES,
            (STATE_NOTE,),
            FAILED_NOTICE,
        ),
    ],
)
async def test_sin_resumen_el_reporte_sale_igual_con_un_aviso(
    summarizer: Summarizer | None,
    prices: LLMPrices | None,
    rows: tuple[ArticleItem, ...],
    notice: str,
) -> None:
    row = search()
    store = Store()

    data = await build(row, rows=rows, store=store, summarizer=summarizer, prices=prices).execute(
        row.search_id, ReportFormat.PDF, ACTOR
    )

    assert (data.summary, data.summary_notice) == (None, notice)
    assert store.saved == []
    assert len(store.generated) == 1


async def test_sigue_el_cursor_cuando_hay_mas_de_una_pagina(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reports, "MAX_ARTICLE_PAGE_SIZE", 2)
    row = search()
    # El lector falso usa el id del cursor como posición: ids 1..5.
    articles = Articles([item(i) for i in range(1, 6)])

    use = BuildReport(
        searches=Reader(row),
        articles=articles,
        regions=FakeRegionRepository(),
        store=Store(),
        static_map=Map(),
        summarizer=None,
        prices=None,
        clock=lambda: NOW,
    )
    data = await use.execute(row.search_id, ReportFormat.PDF, ACTOR)

    assert [a.article_id for a in data.articles] == [1, 2, 3, 4, 5]
    assert articles.pages == 3


@pytest.mark.parametrize("status", [SearchStatus.PENDING, SearchStatus.RUNNING])
async def test_una_busqueda_sin_terminar_no_tiene_reporte(status: SearchStatus) -> None:
    row = search(status)
    store = Store()

    with pytest.raises(SearchNotFinishedError) as error:
        await build(row, store=store).execute(row.search_id, ReportFormat.PDF, ACTOR)

    assert error.value.details == {"id": str(row.search_id), "status": status.value}
    assert store.generated == []


async def test_busqueda_inexistente_o_region_borrada() -> None:
    row = search()

    with pytest.raises(SearchNotFoundError):
        await build(row).execute(uuid4(), ReportFormat.PDF, ACTOR)
    with pytest.raises(RegionNotFoundError):
        await build(row, regions=FakeRegionRepository(())).execute(
            row.search_id, ReportFormat.PDF, ACTOR
        )


async def test_exportar_junta_las_notas_y_lo_deja_en_la_bitacora() -> None:
    row = search(SearchStatus.PARTIAL)
    store = Store()
    use = ExportSearch(
        Reader(row), Articles([IZTAPALAPA_NOTE]), FakeRegionRepository(), store, lambda: NOW
    )

    data = await use.execute(row.search_id, ReportFormat.CSV, ACTOR)

    assert (data.breadcrumb, data.generated_at) == ("México › Ciudad de México", NOW)
    assert [a.article_id for a in data.articles] == [1]
    assert store.generated == [(row.search_id, "csv", ACTOR)]
    running = search(SearchStatus.RUNNING)
    with pytest.raises(SearchNotFinishedError):
        await ExportSearch(
            Reader(running), Articles([]), FakeRegionRepository(), store, lambda: NOW
        ).execute(running.search_id, ReportFormat.GEOJSON, ACTOR)


async def test_reporte_de_todo_mexico_cuenta_por_estado_y_deja_fuera_lo_de_otro_pais() -> None:
    row = replace(search(), region_id=MEXICO.id, region_code="MEX", region_name="México")

    data = await build(row).execute(row.search_id, ReportFormat.PDF, ACTOR)

    assert (data.breadcrumb, data.level) == ("México", AggregateLevel.STATE)
    # La CDMX junta sus 4 notas (alcaldías y "solo CDMX"); París queda fuera.
    assert [(c.code, c.count) for c in data.counts] == [("09", 4), ("14", 1), ("16", 1)]
    assert (data.outside, data.coarser, data.unlocated) == (1, 0, 1)


async def test_la_localidad_cabecera_homonima_cuenta_como_su_alcaldia() -> None:
    # Búsqueda real del 20/10/2026 en "Localidad Miguel Hidalgo" (090160001): la
    # pantalla decía 8 notas dentro y el PDF "0 en Miguel Hidalgo · 11 fuera",
    # porque el reporte no usaba la regla de ``seat_area`` (ADR-0020).
    seat = make_region(
        6, "Iztapalapa", RegionLevel.LOCALITY, parent_id=3, code="090070001", prefix="Localidad"
    )
    row = replace(search(), region_id=seat.id, region_code=seat.code, region_name=seat.name)
    static_map = Map()

    data = await build(
        row, regions=FakeRegionRepository((*ALL, seat)), static_map=static_map
    ).execute(row.search_id, ReportFormat.PDF, ACTOR)

    # Las 2 notas de la alcaldía Iztapalapa (09007) quedan dentro; fuera, el resto.
    assert (data.outside, data.unlocated) == (5, 1)
    assert data.level is AggregateLevel.LOCALITY
    # La portada y el mapa hablan de la búsqueda, pero cuentan sobre la alcaldía.
    assert data.region.code == "090070001"
    assert static_map.calls[0][0].code == "09007"
