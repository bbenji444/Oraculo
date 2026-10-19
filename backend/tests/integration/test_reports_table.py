"""Reglas de la tabla ``reports`` que garantiza la base (§6, ADR-0018)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from tests.integration.test_pipeline_tables import new_search

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]

_INSERT = text(
    "INSERT INTO reports (search_id, executive_summary, llm_provider, llm_model, "
    "prompt_version, llm_tokens_in, llm_tokens_out, llm_cost_usd, created_by) "
    "VALUES (:search, 'Resumen', 'openai', 'gpt-6-luna', 'summary_v1', 900, 200, :cost, "
    "'prueba') RETURNING id"
)


@pytest.fixture
def conn(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Iterator[Connection]:
    monkeypatch.setenv("ALEMBIC_TARGET", "test")
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()
    engine.dispose()


def test_un_solo_resumen_por_busqueda(conn: Connection) -> None:
    search = new_search(conn, "completed")
    conn.execute(_INSERT, {"search": search, "cost": 0.0012})

    # El resumen se reutiliza: una segunda fila para la misma búsqueda es un error.
    with pytest.raises(IntegrityError, match="reports_search_id_key"):
        conn.execute(_INSERT, {"search": search, "cost": 0.0012})


def test_el_costo_no_puede_ser_negativo(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="reports_usage_non_negative"):
        conn.execute(_INSERT, {"search": new_search(conn, "completed"), "cost": -1})


def test_borrar_la_busqueda_borra_su_resumen(conn: Connection) -> None:
    search = new_search(conn, "completed")
    conn.execute(_INSERT, {"search": search, "cost": 0})

    conn.execute(text("DELETE FROM searches WHERE id = :id"), {"id": search})

    left = conn.execute(text("SELECT count(*) FROM reports WHERE search_id = :id"), {"id": search})
    assert left.scalar_one() == 0


def test_se_busca_por_search_id_con_indice(conn: Connection) -> None:
    indexes = conn.execute(
        text("SELECT indexdef FROM pg_indexes WHERE tablename = 'reports'")
    ).scalars()

    assert any("(search_id)" in definition for definition in indexes)
