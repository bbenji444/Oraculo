"""``make revisar-relevancia`` (ADR-0114) con lecturas en memoria: sin base ni gasto."""

import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.pagination import TimeCursor
from app.application.ports.search_reads import (
    ArticleFilters,
    ArticleItem,
    ConceptRef,
    InRegion,
    JudgementView,
    SearchDetail,
)
from app.application.ports.search_store import SearchConcept, StoredSearch
from app.application.use_cases.review_relevance import (
    REVIEW_PAGE_SIZE,
    ReviewRelevance,
    ordered,
    review_row,
)
from app.application.use_cases.run_search import SearchNotFoundError
from app.cli.revisar_relevancia import (
    READ_ONLY_OPTIONS,
    REASON_CHARS,
    TITLE_CHARS,
    parse_args,
    progress_lines,
    render,
    row_line,
    show_review,
)
from app.domain.authority import RelevanceBand
from app.domain.concept import QueryMode
from app.domain.enrichment import LLMUsage
from app.domain.search import SearchStatus

pytestmark = pytest.mark.anyio

SEARCH_ID = UUID("2b3e0d6c-0000-4000-8000-000000000035")
T0 = datetime(2026, 11, 18, 18, tzinfo=UTC)
RAPIDA = SearchConcept(
    9,
    "hacker eternal",
    "hacker eternal en todo el mundo",
    ("hacker eternal", "Eternal filtra datos"),
    query_mode=QueryMode.OPEN,
    required_terms=("eternal",),
)
PROGRESS: dict[str, object] = {
    "stage": "close",
    "outside_window": 2,
    "off_core": 3,
    "off_core_samples": ["Concentración feminista en Guadalajara", "Cancelan vuelos"],
    "articles": 4,
    "skipped_by_cap": 0,
}


def detail(progress: dict[str, object] | None = None) -> SearchDetail:
    return SearchDetail(
        search_id=SEARCH_ID,
        user_id="benji",
        status=SearchStatus.COMPLETED,
        region_id=0,
        region_code="WORLD",
        region_name="Mundo",
        date_from=date(2026, 11, 12),
        date_to=date(2026, 11, 18),
        concepts=(ConceptRef(9, "hacker eternal"),),
        progress=progress if progress is not None else PROGRESS,
        queries_planned=3,
        credits_estimated=1,
        credits_used=1,
        llm_usage=LLMUsage(10, 1),
        llm_cost_usd=0.0001,
        results_count=4,
        error_summary=None,
        created_at=T0,
        started_at=None,
        finished_at=None,
    )


def item(
    article_id: int,
    title: str,
    *judgements: JudgementView,
    in_region: bool | None = True,
    minutes: int = 0,
) -> ArticleItem:
    return ArticleItem(
        article_id=article_id,
        title=title,
        source_name=None,
        source_domain=None,
        url=f"https://medio.mx/{article_id}",
        published_at=T0 - timedelta(minutes=minutes),
        summary=None,
        event_type=None,
        event_date=None,
        extraction_status="fallback",
        enrichment_status="ok",
        judgements=judgements,
        primary=None,
        in_region=in_region,
        providers=("google_news_rss", "searchapi_web", "google_news_rss"),
    )


def judged(relevant: bool, score: float, reason: str = "Razón.", concept: int = 9) -> JudgementView:
    # La búsqueda rápida es un concepto abierto: usa las cuatro bandas (ADR-0114).
    return JudgementView(concept, "hacker eternal", relevant, score, reason, QueryMode.OPEN)


ETERNAL = item(1, "El hacker Eternal filtra datos del IMSS", judged(True, 0.92))
BURO = item(
    2,
    "Hackean Buró Laboral y exponen datos de miles de trabajadores",
    judged(
        True, 0.7, "El buscador la encontró por «hacker eternal»; el título no nombra a Eternal."
    ),
)
OTHER_GROUP = item(3, "LockBit ataca a un banco", judged(False, 0.45), in_region=False)
MOVIE = item(4, "Eternal Sunshine vuelve a los cines", judged(False, 0.1))
UNJUDGED = item(5, "Sin juicio por el tope", in_region=None)


class Searches:
    """``SearchCopyReaderPort`` en memoria."""

    def __init__(self, found: bool = True, progress: dict[str, object] | None = None) -> None:
        self.found = found
        self.progress = progress
        self.loaded: list[UUID] = []

    async def load(self, search_id: UUID) -> StoredSearch | None:
        self.loaded.append(search_id)
        if not self.found:
            return None
        return StoredSearch(
            search_id=search_id,
            user_id="benji",
            region_id=0,
            region_code="WORLD",
            date_from=date(2026, 11, 12),
            date_to=date(2026, 11, 18),
            status=SearchStatus.COMPLETED,
            concepts=(RAPIDA,),
        )

    async def search_detail(self, search_id: UUID) -> SearchDetail | None:
        return detail(self.progress) if self.found else None

    async def last_search_id(self) -> UUID | None:
        return SEARCH_ID if self.found else None


class Articles:
    """``SearchArticlesReaderPort`` en memoria, con páginas de verdad."""

    def __init__(self, items: list[ArticleItem]) -> None:
        self.items = items
        self.calls: list[tuple[ArticleFilters, TimeCursor | None, int]] = []

    async def search_articles(
        self, search_id: UUID, filters: ArticleFilters, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        self.calls.append((filters, after, limit))
        start = 0
        if after is not None:
            start = next(i for i, a in enumerate(self.items) if str(a.article_id) == after.id) + 1
        return self.items[start : start + limit]


async def test_la_revision_junta_pedido_contadores_y_notas_por_banda() -> None:
    articles = Articles([UNJUDGED, MOVIE, OTHER_GROUP, BURO, ETERNAL])

    review = await ReviewRelevance(Searches(), articles).execute()

    assert [r.article_id for r in review.rows] == [1, 2, 3, 4, 5]
    assert review.band_counts() == {
        RelevanceBand.RELEVANT: 1,
        RelevanceBand.UNCONFIRMED: 1,
        RelevanceBand.RELATED: 1,
        RelevanceBand.UNRELATED: 1,
        None: 1,
    }
    assert review.outside_region() == 1
    assert review.concepts == (RAPIDA,)
    assert review.progress["off_core"] == 3
    # Pide todas: relevantes o no y de cualquier región.
    filters = articles.calls[0][0]
    assert (filters.relevant_only, filters.in_region) == (False, InRegion.ALL)


async def test_lee_todas_las_paginas() -> None:
    many = [
        item(i, f"Nota {i}", judged(False, 0.1), minutes=i) for i in range(1, REVIEW_PAGE_SIZE + 6)
    ]
    articles = Articles(many)

    review = await ReviewRelevance(Searches(), articles).execute(SEARCH_ID)

    assert len(review.rows) == REVIEW_PAGE_SIZE + 5
    assert len(articles.calls) == 2
    assert articles.calls[1][1] == TimeCursor(many[REVIEW_PAGE_SIZE - 1].published_at, "200")


async def test_sin_busqueda_avisa() -> None:
    with pytest.raises(SearchNotFoundError):
        await ReviewRelevance(Searches(found=False), Articles([])).execute()
    with pytest.raises(SearchNotFoundError):
        await ReviewRelevance(Searches(found=False), Articles([])).execute(uuid4())


def test_la_fila_usa_el_mejor_juicio_entre_conceptos() -> None:
    two = item(7, "Dos conceptos", judged(False, 0.4, concept=3), judged(True, 0.85))

    row = review_row(two)

    assert (row.band, row.score, row.concept) == (RelevanceBand.RELEVANT, 0.85, "hacker eternal")


def test_dentro_de_cada_banda_va_del_puntaje_mas_alto_al_mas_bajo() -> None:
    rows = [
        review_row(item(1, "B", judged(False, 0.35))),
        review_row(item(2, "A", judged(False, 0.55))),
        review_row(item(3, "C", judged(True, 0.65))),
    ]

    assert [r.article_id for r in ordered(rows)] == [3, 2, 1]


async def test_la_pantalla_muestra_el_pedido_los_contadores_y_las_filas() -> None:
    review = await ReviewRelevance(Searches(), Articles([BURO, ETERNAL, OTHER_GROUP])).execute()

    lines = render(review)
    text = "\n".join(lines)

    assert lines[0] == f"Búsqueda {SEARCH_ID} · Región: Mundo · 12/11/2026 a 18/11/2026"
    assert "Concepto «hacker eternal» (como en Google)" in text
    assert "  Pidió: hacker eternal en todo el mundo" in text
    assert "  Frases: hacker eternal | Eternal filtra datos" in text
    assert "  Debe hablar de: eternal" in text
    assert "fuera del periodo: 2 · sin lo pedido (filtro de palabras): 3" in text
    assert "   - Concentración feminista en Guadalajara" in text
    assert (
        "Bandas: relevantes 1 · por confirmar 1 · cercanas 1 · ajenas 0 · sin juicio 0"
        " · fuera de la región 1"
    ) in text
    first = row_line(review.rows[0])
    assert first.startswith("relevante     |  0.92 | dentro | fallback | ")
    # Los proveedores se muestran una vez cada uno.
    assert "google_news_rss, searchapi_web" in first
    assert lines[-3:] == [row_line(r) for r in review.rows]


def test_titulo_y_razon_se_recortan() -> None:
    long = item(9, "T" * 200, judged(False, 0.4, "R" * 300))

    line = row_line(review_row(long))

    assert "T" * (TITLE_CHARS - 1) + "…" in line
    assert "T" * TITLE_CHARS not in line
    assert line.endswith("R" * (REASON_CHARS - 1) + "…")


def test_sin_contadores_lo_dice() -> None:
    assert progress_lines({"stage": "close"}) == ["Avance: sin contadores"]


async def test_el_comando_imprime_y_termina_bien(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    code = await show_review(None, Searches(), Articles([ETERNAL]))

    assert code == 0
    assert "El hacker Eternal filtra datos del IMSS" in caplog.text
    assert "solo lectura" in caplog.text


async def test_el_comando_sin_busqueda_sale_con_1(caplog: pytest.LogCaptureFixture) -> None:
    code = await show_review(uuid4(), Searches(found=False), Articles([]))

    assert code == 1
    assert "No existe la búsqueda" in caplog.text


def test_opciones_y_conexion_de_solo_lectura() -> None:
    assert parse_args(["--busqueda", str(SEARCH_ID)]).busqueda == SEARCH_ID
    assert parse_args([]).busqueda is None
    assert READ_ONLY_OPTIONS == "-c default_transaction_read_only=on"
