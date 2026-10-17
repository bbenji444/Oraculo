"""Registro de peticiones a proveedores contra la base de pruebas."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.providers.gdelt import GdeltProvider
from app.adapters.providers.http import ProviderHttpClient
from app.application.audit import Actor
from app.application.ports.provider_log import ProviderQueryRecord, QueryStatus
from app.cli.diagnostico_gdelt import d1_query
from app.cli.probar_proveedor import Plan, execute
from app.core.config import Settings
from app.domain.concept import Concept, ConceptDraft
from app.domain.queries import Provider

SEED_CONCEPT = Concept(
    id=1,
    data=ConceptDraft.validated(
        name="Diagnóstico",
        description="",
        keywords=("gobierno",),
        exclude_terms=(),
        color="#000000",
    ),
    created_by="prueba",
    created_at=datetime(2026, 10, 16, tzinfo=UTC),
    updated_at=datetime(2026, 10, 16, tzinfo=UTC),
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _empty(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provider_queries"))
        conn.execute(text("DELETE FROM audit_log"))


@pytest.fixture
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    _empty(engine)
    yield engine
    _empty(engine)
    engine.dispose()


def record(
    provider: str = "searchapi", status: QueryStatus = "ok", cost_credits: int = 1
) -> ProviderQueryRecord:
    return ProviderQueryRecord(
        provider=provider,
        query_text="hackeo CDMX",
        params={"q": "hackeo CDMX", "gl": "mx"},
        status=status,
        http_status=200,
        results_count=10,
        cost_credits=cost_credits,
        duration_ms=850,
    )


async def test_guarda_la_peticion_y_su_auditoria(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    log = PostgresProviderQueryLog(test_engine)

    row_id = await log.record(record(), Actor("benji", "127.0.0.1"))

    with sync_engine.connect() as conn:
        saved = conn.execute(
            text("SELECT provider, params, status, cost_credits FROM provider_queries")
        ).one()
        audit = conn.execute(
            text("SELECT user_id, action, entity_id, payload->>'creditos' FROM audit_log")
        ).one()
    assert tuple(saved) == ("searchapi", {"q": "hackeo CDMX", "gl": "mx"}, "ok", 1)
    assert tuple(audit) == ("benji", "provider.query_executed", str(row_id), "1")


async def test_sin_actor_no_escribe_en_la_bitacora(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    await PostgresProviderQueryLog(test_engine).record(record())

    with sync_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == 0


async def test_suma_los_creditos_del_periodo_por_proveedor(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    log = PostgresProviderQueryLog(test_engine)
    for _ in range(3):
        await log.record(record())
    await log.record(record(provider="gdelt", cost_credits=0))
    await log.record(record(status="error", cost_credits=0))
    with sync_engine.begin() as conn:
        # Una petición del mes pasado no cuenta.
        conn.execute(
            text(
                "UPDATE provider_queries SET created_at = now() - interval '40 days' "
                "WHERE id = (SELECT min(id) FROM provider_queries)"
            )
        )

    since = datetime.now(UTC) - timedelta(days=30)

    assert await log.credits_used_since("searchapi", since) == 2
    assert await log.credits_used_since("gdelt", since) == 0


async def test_un_vacio_despues_de_429_queda_como_falla_en_provider_queries(
    test_engine: AsyncEngine, sync_engine: Engine
) -> None:
    # ADR-0012: reproduce D2 del diagnóstico (429, 429, 200 con {}) de punta a
    # punta: adaptador de GDELT → comando de prueba → PostgreSQL.
    responses = [
        httpx2.Response(429, text="Please limit requests to one every 5 seconds"),
        httpx2.Response(429, text="Please limit requests to one every 5 seconds"),
        httpx2.Response(200, text="{}"),
    ]

    async def no_wait(_seconds: float) -> None:
        return None

    http = ProviderHttpClient(
        Provider.GDELT,
        timeout_seconds=5,
        max_attempts=3,
        max_concurrency=1,
        transport=httpx2.MockTransport(lambda _request: responses.pop(0)),
        sleep=no_wait,
    )
    provider = GdeltProvider(http, enabled=True)
    query = d1_query(date(2026, 10, 16))
    plan = Plan(
        concept=SEED_CONCEPT,
        breadcrumb="—",
        query=query,
        params=provider.request_params(query),
        credits=0,
    )

    result = await execute(
        provider=provider, plan=plan, log=PostgresProviderQueryLog(test_engine), actor=Actor("x")
    )

    assert result is None
    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, results_count, error_message FROM provider_queries")
        ).one()
    assert (row.status, row.results_count) == ("error", 0)
    assert "no como 'sin resultados'" in row.error_message
