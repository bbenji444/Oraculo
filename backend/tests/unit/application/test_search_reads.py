"""Lecturas de búsquedas: cursor de fecha + id, historial y detalle (sin base)."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.pagination import (
    NameCursor,
    TimeCursor,
    decode_time_cursor,
    encode_cursor,
    encode_time_cursor,
)
from app.application.ports.search_reads import (
    ArticleDetail,
    ArticleFilters,
    ArticleItem,
    CategoryCount,
    ConceptRef,
    InRegion,
    RegionPoint,
    SearchDetail,
)
from app.application.use_cases.run_search import SearchNotFoundError
from app.application.use_cases.search_reads import (
    ArticleNotFoundError,
    GetAggregates,
    GetArticle,
    GetSearch,
    ListSearchArticles,
    ListSearches,
)
from app.domain.aggregates import AggregateLevel, NoteLocation
from app.domain.enrichment import LLMUsage
from app.domain.errors import InvalidRequestError
from app.domain.geocoding import Precision
from app.domain.search import SearchStatus

pytestmark = pytest.mark.anyio

T0 = datetime(2026, 10, 17, 18, tzinfo=UTC)


def detail(minutes_ago: int) -> SearchDetail:
    return SearchDetail(
        search_id=uuid4(),
        user_id="benji",
        status=SearchStatus.COMPLETED,
        region_id=14,
        region_code="14",
        region_name="Jalisco",
        date_from=date(2026, 10, 10),
        date_to=date(2026, 10, 17),
        concepts=(ConceptRef(3, "Extorsión"),),
        progress={"stage": "close"},
        queries_planned=2,
        credits_estimated=1,
        credits_used=1,
        llm_usage=LLMUsage(10, 1),
        llm_cost_usd=0.0001,
        results_count=18,
        error_summary=None,
        created_at=T0 - timedelta(minutes=minutes_ago),
        started_at=None,
        finished_at=None,
    )


class Reader:
    def __init__(self, rows: list[SearchDetail]) -> None:
        self.rows = sorted(rows, key=lambda d: (d.created_at, str(d.search_id)), reverse=True)

    async def search_detail(self, search_id: UUID) -> SearchDetail | None:
        return next((d for d in self.rows if d.search_id == search_id), None)

    async def history(
        self, user_id: str, after: TimeCursor | None, limit: int
    ) -> list[SearchDetail]:
        rows = [d for d in self.rows if d.user_id == user_id]
        if after is not None:
            assert after.moment is not None
            key = (after.moment, after.id)
            rows = [d for d in rows if (d.created_at, str(d.search_id)) < key]
        return rows[:limit]


@pytest.mark.parametrize("moment", [T0, None])
def test_el_cursor_de_fecha_ida_y_vuelta(moment: datetime | None) -> None:
    cursor = TimeCursor(moment, "42")

    assert decode_time_cursor(encode_time_cursor(cursor)) == cursor


@pytest.mark.parametrize(
    "token", ["no-es-base64!!", "W10", encode_cursor(NameCursor("JALISCO", 14))]
)
def test_cursor_danado_o_de_otra_lista(token: str) -> None:
    with pytest.raises(InvalidRequestError, match="cursor"):
        decode_time_cursor(token)


async def test_historial_por_paginas_de_la_mas_reciente_a_la_mas_vieja() -> None:
    rows = [detail(m) for m in (1, 2, 3)]
    other = replace(detail(0), user_id="otra-persona")
    use = ListSearches(Reader([*rows, other]))

    first = await use.execute("benji", limit=2)
    second = await use.execute("benji", first.next_cursor, limit=2)

    assert [d.search_id for d in first.items] == [rows[0].search_id, rows[1].search_id]
    assert [d.search_id for d in second.items] == [rows[2].search_id]
    assert second.next_cursor is None


@pytest.mark.parametrize("limit", [0, 101])
async def test_limite_fuera_de_rango(limit: int) -> None:
    with pytest.raises(InvalidRequestError, match="límite"):
        await ListSearches(Reader([])).execute("benji", limit=limit)


async def test_detalle_o_404() -> None:
    row = detail(1)
    use = GetSearch(Reader([row]))

    assert await use.execute(row.search_id) == row
    with pytest.raises(SearchNotFoundError):
        await use.execute(uuid4())


def item(article_id: int, published: datetime | None) -> ArticleItem:
    return ArticleItem(
        article_id,
        f"Nota {article_id}",
        None,
        None,
        "https://x.mx",
        published,
        None,
        None,
        None,
        "ok",
        "ok",
        (),
        None,
        None,
        ("searchapi",),
    )


class Articles:
    def __init__(self, rows: list[ArticleItem]) -> None:
        self.rows = rows
        self.asked: list[tuple[ArticleFilters, TimeCursor | None]] = []

    async def search_articles(
        self, search_id: UUID, filters: ArticleFilters, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        self.asked.append((filters, after))
        start = (
            0
            if after is None
            else next(i + 1 for i, r in enumerate(self.rows) if str(r.article_id) == after.id)
        )
        return self.rows[start : start + limit]

    async def article_detail(self, article_id: int) -> ArticleDetail | None:
        return None

    async def note_locations(self, search_id: UUID, filters: ArticleFilters) -> list[NoteLocation]:
        return [
            NoteLocation("14039", "MEX", Precision.MUNICIPALITY),
            NoteLocation("14", "MEX", Precision.STATE),
            NoteLocation("17006", "MEX", Precision.MUNICIPALITY),
            # Clave que ya no está en el catálogo: no se pinta.
            NoteLocation("99001", "MEX", Precision.MUNICIPALITY),
        ]

    async def category_counts(
        self, search_id: UUID, filters: ArticleFilters
    ) -> list[CategoryCount]:
        # Sin categorías en estas pruebas (F12.4 se prueba aparte).
        return []

    async def regions_by_code(self, codes: Sequence[str]) -> list[RegionPoint]:
        known = {"14": "Jalisco", "17": "Morelos"}
        return [
            RegionPoint(i, c, known[c], -100.0, 20.0) for i, c in enumerate(codes) if c in known
        ]


async def test_notas_por_paginas_y_validacion() -> None:
    search = detail(1)
    articles = Articles([item(3, T0), item(2, None)])
    use = ListSearchArticles(Reader([search]), articles)
    filters = ArticleFilters(in_region=InRegion.INSIDE)

    first = await use.execute(search.search_id, filters, limit=1)
    second = await use.execute(search.search_id, filters, first.next_cursor, limit=1)

    assert [i.article_id for i in first.items] == [3]
    assert [i.article_id for i in second.items] == [2]
    assert second.next_cursor is None
    assert articles.asked[1] == (filters, TimeCursor(T0, "3"))
    with pytest.raises(InvalidRequestError, match="galaxia"):
        await use.execute(search.search_id, ArticleFilters(precisions=frozenset({"galaxia"})))
    with pytest.raises(SearchNotFoundError):
        await use.execute(uuid4(), filters)
    with pytest.raises(ArticleNotFoundError):
        await GetArticle(articles).execute(1)


async def test_mapa_de_calor_ordenado_y_sin_regiones_desconocidas() -> None:
    search = detail(1)

    view = await GetAggregates(Reader([search]), Articles([])).execute(
        search.search_id, AggregateLevel.STATE, ArticleFilters()
    )

    assert [(i.region.name, i.count) for i in view.items] == [("Jalisco", 2), ("Morelos", 1)]
    assert (view.coarser, view.abroad, view.unlocated, view.total) == (0, 0, 0, 4)
    with pytest.raises(SearchNotFoundError):
        await GetAggregates(Reader([]), Articles([])).execute(
            uuid4(), AggregateLevel.STATE, ArticleFilters()
        )
