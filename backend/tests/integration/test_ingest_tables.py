"""Reglas de las tablas news_index e ingest_runs que garantiza la base."""

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
        connection.execute(text("DELETE FROM news_index"))
        connection.execute(text("DELETE FROM ingest_runs"))
        yield connection
        transaction.rollback()
    engine.dispose()


def add_news(conn: Connection, url: str = "https://medio.mx/nota", title: str = "Hackeo") -> None:
    conn.execute(
        text(
            "INSERT INTO news_index (source, url, url_hash, title, published_at, text_norm) "
            "VALUES ('gdelt_gkg', :url, md5(:url), :title, now(), upper(:title))"
        ),
        {"url": url, "title": title},
    )


def test_una_url_se_guarda_una_sola_vez(conn: Connection) -> None:
    add_news(conn)

    with pytest.raises(IntegrityError, match="news_index_url_hash_key"):
        add_news(conn)


@pytest.mark.parametrize(
    ("url", "title", "constraint"),
    [
        ("javascript:alert(1)", "x", "news_index_url_web"),
        ("https://medio.mx/otra", "   ", "news_index_title_not_blank"),
    ],
)
def test_url_web_y_titulo_no_vacio(conn: Connection, url: str, title: str, constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        add_news(conn, url, title)


def add_run(conn: Connection, status: str, dedupe_key: str | None) -> None:
    conn.execute(
        text(
            "INSERT INTO ingest_runs (source, item, dedupe_key, status) "
            "VALUES ('gdelt_gkg', 'archivo', :key, :status)"
        ),
        {"key": dedupe_key, "status": status},
    )


def test_un_archivo_exitoso_no_se_registra_dos_veces(conn: Connection) -> None:
    add_run(conn, "ok", "20261016191500.translation.gkg.csv.zip")

    with pytest.raises(IntegrityError, match="ingest_runs_dedupe_ok_key"):
        add_run(conn, "ok", "20261016191500.translation.gkg.csv.zip")


def test_reintentar_un_archivo_fallido_si_se_permite(conn: Connection) -> None:
    add_run(conn, "error", "archivo.zip")
    add_run(conn, "error", "archivo.zip")
    add_run(conn, "ok", "archivo.zip")
    # Los feeds RSS no usan llave: se leen en cada corrida.
    add_run(conn, "ok", None)
    add_run(conn, "ok", None)


def test_estado_desconocido_se_rechaza(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="ingest_runs_status_known"):
        add_run(conn, "quizas", None)


def test_existen_los_indices(conn: Connection) -> None:
    names = set(
        conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE tablename IN ('news_index', 'ingest_runs')"
            )
        ).scalars()
    )

    assert {
        "news_index_url_hash_key",
        "news_index_text_trgm",
        "news_index_published_id",
        "news_index_gdelt_states",
        "news_index_source_published",
        "ingest_runs_source_started",
        "ingest_runs_dedupe_ok_key",
    } <= names
