"""Resumen guardado, proveedores y bitácora de reportes contra la base de pruebas."""

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.reports_repository import PostgresReportStore
from app.application.audit import Actor
from app.application.ports.reports import ProviderUsage, StoredSummary
from app.core.config import Settings
from app.domain.enrichment import LLMUsage
from tests.integration.test_pipeline_tables import new_search

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
ACTOR = Actor("prueba", "10.0.0.7")
SUMMARY = StoredSummary(
    "Predomina el cobro de piso en Peñón Blanco.",
    "openai",
    "gpt-6-luna",
    "summary_v1",
    LLMUsage(2000, 300),
    0.0004,
)


@pytest.fixture
def search_id(settings: Settings) -> Iterator[UUID]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine: Engine = create_engine(settings.database_url(test=True))
    with engine.begin() as conn:
        found = UUID(new_search(conn, "completed"))
        conn.execute(
            text(
                "INSERT INTO provider_queries (search_id, provider, query_text, status, "
                "results_count, from_cache, cost_credits) VALUES "
                "(:id, 'searchapi', 'q1', 'ok', 10, false, 1), "
                "(:id, 'searchapi', 'q2', 'ok', 4, true, 0), "
                "(:id, 'indice_local', 'q1', 'ok', 3, false, 0), "
                "(:id, 'gdelt', 'q1', 'error', 0, false, 0)"
            ),
            {"id": found},
        )
    yield found
    with engine.begin() as conn:
        # Borrar la búsqueda arrastra su resumen; sus consultas quedan sin búsqueda.
        conn.execute(text("DELETE FROM provider_queries WHERE search_id = :id"), {"id": found})
        conn.execute(text("DELETE FROM audit_log WHERE entity_id = :id"), {"id": str(found)})
        conn.execute(text("DELETE FROM searches WHERE id = :id"), {"id": found})
    engine.dispose()


async def test_el_resumen_se_guarda_una_vez_y_se_lee_igual(
    test_engine: AsyncEngine, search_id: UUID
) -> None:
    store = PostgresReportStore(test_engine)
    assert await store.summary(search_id) is None

    await store.save_summary(search_id, SUMMARY, ACTOR)
    # Un segundo reporte que también lo pagó no lo reemplaza.
    await store.save_summary(
        search_id, StoredSummary("Otro", "x", "y", "z", LLMUsage(1, 1), 0), ACTOR
    )

    assert await store.summary(search_id) == SUMMARY


async def test_uso_de_cada_proveedor_de_la_busqueda(
    test_engine: AsyncEngine, search_id: UUID
) -> None:
    usage = await PostgresReportStore(test_engine).provider_usage(search_id)

    assert usage == [
        ProviderUsage("gdelt", 1, 0, 0, 0, 1),
        ProviderUsage("indice_local", 1, 3, 0, 0, 0),
        ProviderUsage("searchapi", 2, 14, 1, 1, 0),
    ]


async def test_cada_reporte_queda_en_la_bitacora(test_engine: AsyncEngine, search_id: UUID) -> None:
    store = PostgresReportStore(test_engine)
    await store.record_generated(search_id, "pdf", ACTOR)
    await store.record_generated(search_id, "csv", Actor("otra"))

    async with test_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT user_id, action, entity_type, payload, host(ip) AS ip "
                    "FROM audit_log WHERE entity_id = :id ORDER BY id"
                ),
                {"id": str(search_id)},
            )
        ).all()

    assert [tuple(r) for r in rows] == [
        ("prueba", "report.generated", "search", {"formato": "pdf"}, "10.0.0.7"),
        ("otra", "report.generated", "search", {"formato": "csv"}, None),
    ]
