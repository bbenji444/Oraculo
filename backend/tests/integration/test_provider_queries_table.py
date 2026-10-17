"""Reglas de la tabla provider_queries que garantiza la propia base de datos."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def conn(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Iterator[Connection]:
    monkeypatch.setenv("ALEMBIC_TARGET", "test")
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("DELETE FROM provider_queries"))
        yield connection
        transaction.rollback()
    engine.dispose()


def insert(conn: Connection, **values: object) -> None:
    data: dict[str, object] = {
        "provider": "gdelt",
        "query_text": "hackeo CDMX",
        "status": "ok",
        "from_cache": False,
        "cost_credits": 0,
    }
    data.update(values)
    conn.execute(
        text(
            "INSERT INTO provider_queries (provider, query_text, status, from_cache, cost_credits) "
            "VALUES (:provider, :query_text, :status, :from_cache, :cost_credits)"
        ),
        data,
    )


def test_valores_por_defecto(conn: Connection) -> None:
    insert(conn)

    row = conn.execute(
        text(
            "SELECT search_id, params, results_count, duration_ms, error_message "
            "FROM provider_queries"
        )
    ).one()

    assert tuple(row) == (None, {}, 0, 0, None)


def test_estado_desconocido_se_rechaza(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="provider_queries_status_known"):
        insert(conn, status="quizas")


def test_una_respuesta_de_cache_no_puede_costar_creditos(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="provider_queries_cache_is_free"):
        insert(conn, provider="searchapi", from_cache=True, cost_credits=1)


def test_existen_los_indices(conn: Connection) -> None:
    names = set(
        conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'provider_queries'")
        ).scalars()
    )

    assert {
        "provider_queries_provider_created",
        "provider_queries_search",
        "provider_queries_created_id",
    } <= names
