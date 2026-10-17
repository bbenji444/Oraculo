"""Comando ``make buscar``: lo que muestra y cómo espera al worker (sin red ni base)."""

import logging
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.persistence.search_repository import ResultPreview, SearchSnapshot
from app.application.ports.llm import LLMInfo
from app.application.ports.search_store import NewSearch, SearchConcept
from app.application.use_cases.plan_search import SearchEstimate
from app.cli import buscar
from app.domain.enrichment import LLMUsage
from app.domain.search import SearchStatus

pytestmark = pytest.mark.anyio


def snapshot(status: SearchStatus, **progress: object) -> SearchSnapshot:
    return SearchSnapshot(status, dict(progress), 1, LLMUsage(2000, 300), 0.00035, None)


def test_el_avance_se_describe_en_espanol() -> None:
    assert buscar.describe_progress({"stage": "query"}) == "Consultando proveedores"
    assert (
        buscar.describe_progress({"stage": "enrich", "articles": 12, "enriched": 10})
        == "Resumiendo y clasificando con la IA (12 notas, 10 resumidas)"
    )
    assert buscar.describe_progress({"stage": "otra"}) == "otra"


def test_los_argumentos_aceptan_varios_conceptos_y_fechas() -> None:
    args = buscar.parse_args(
        ["--concepto", "Extorsión", "--concepto", "Secuestro", "--region", "14", "--aqui"]
    )
    fixed = buscar.parse_args(
        ["--concepto", "X", "--region", "09", "--desde", "2026-10-01", "--hasta", "2026-10-07"]
    )

    assert (args.concepto, args.region, args.dias, args.aqui) == (
        ["Extorsión", "Secuestro"],
        "14",
        7,
        True,
    )
    assert (fixed.desde, fixed.hasta, fixed.aqui) == (date(2026, 10, 1), date(2026, 10, 7), False)


def prepared(credits_month: int) -> SearchEstimate:
    return SearchEstimate(
        search=NewSearch(
            "benji",
            2,
            date(2026, 10, 10),
            date(2026, 10, 16),
            (SearchConcept(3, "Extorsión", "", ("extorsión",)),),
            2,
            1,
        ),
        breadcrumb="México › Ciudad de México",
        queries=(),
        credits=1,
        credits_month=credits_month,
        credits_limit=100,
        llm=LLMInfo("openai", "gpt-6-luna", 0.10, 0.50, configured=True),
        llm_max_articles=150,
        llm_max_cost_usd=0.0525,
    )


def test_el_plan_muestra_creditos_y_costo_maximo(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        buscar.show_prepared(prepared(10))

    assert "Créditos de SearchApi: 1 (este mes van 10 de 100)" in caplog.text
    assert "hasta 150 notas, ~0.0525 USD como máximo" in caplog.text
    assert not prepared(99).over_limit
    assert prepared(100).over_limit


def test_el_resultado_muestra_cinco_ejemplos_con_lugar_y_precision(
    caplog: pytest.LogCaptureFixture,
) -> None:
    located = ResultPreview(
        "Detienen a extorsionadores",
        "Milenio",
        "https://milenio.com/a",
        datetime(2026, 10, 15, 18, tzinfo=UTC),
        "Resumen propio.",
        ("Extorsión",),
        "Alcaldía Iztapalapa",
        "municipality",
        0.95,
        True,
        "ok",
    )
    unlocated = ResultPreview(
        "Otra", None, "https://x.mx/b", None, None, (), None, None, None, None, "fallback"
    )
    final = SearchSnapshot(
        SearchStatus.PARTIAL,
        {"articles": 7, "in_region": 1},
        1,
        LLMUsage(10, 2),
        0.0,
        "searchapi: caído",
    )

    with caplog.at_level(logging.INFO):
        buscar.show_result(final, [located, *([unlocated] * 5)])

    text = caplog.text
    assert "Búsqueda partial" in text
    assert "Notas: 7" in text
    assert "Avisos: searchapi: caído" in text
    assert "5 ejemplos para revisar a mano" in text
    assert "Lugar: Alcaldía Iztapalapa (municipio, confianza 0.95) · dentro de la región" in text
    assert "[15/10/2026] Milenio" in text
    assert "Sin ubicación · —" in text
    assert "ninguno relevante" in text
    assert text.count("Resumen:") == 5


class Store:
    def __init__(self, replies: list[SearchSnapshot | None]) -> None:
        self.replies = replies

    async def snapshot(self, search_id: UUID) -> SearchSnapshot | None:
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


async def test_espera_al_worker_y_avisa_cada_etapa(caplog: pytest.LogCaptureFixture) -> None:
    store = Store(
        [
            None,
            snapshot(SearchStatus.RUNNING, stage="query"),
            snapshot(SearchStatus.RUNNING, stage="query"),
            snapshot(SearchStatus.COMPLETED, stage="close"),
        ]
    )
    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    with caplog.at_level(logging.INFO):
        result = await buscar.wait_for(store, uuid4(), sleep)

    assert result is not None and result.status is SearchStatus.COMPLETED
    assert caplog.text.count("Consultando proveedores") == 1
    assert pauses == [buscar.POLL_SECONDS] * 3


async def test_si_el_worker_no_termina_se_rinde() -> None:
    store = Store([snapshot(SearchStatus.PENDING)])

    async def sleep(seconds: float) -> None:
        return None

    result = await buscar.wait_for(store, uuid4(), sleep, limit_seconds=0.01)

    assert result is None
