"""Lecturas de búsquedas: cursor de fecha + id, historial y detalle (sin base)."""

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
from app.application.ports.search_reads import ConceptRef, SearchDetail
from app.application.use_cases.run_search import SearchNotFoundError
from app.application.use_cases.search_reads import GetSearch, ListSearches
from app.domain.enrichment import LLMUsage
from app.domain.errors import InvalidRequestError
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
