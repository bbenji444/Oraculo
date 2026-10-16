"""Tabla audit_log: estructura e índices."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DataError

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
        yield connection
        transaction.rollback()
    engine.dispose()


def test_guarda_un_cambio_con_su_ip_y_datos(conn: Connection) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
            "VALUES ('desarrollo', 'concept.created', 'concept', '7', "
            """'{"after": {"name": "Extorsión"}}', '127.0.0.1')"""
        )
    )

    row = conn.execute(
        text("SELECT action, payload, host(ip), created_at IS NOT NULL FROM audit_log")
    ).one()

    assert tuple(row) == ("concept.created", {"after": {"name": "Extorsión"}}, "127.0.0.1", True)


def test_la_ip_es_opcional_pero_valida(conn: Connection) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_log (user_id, action, entity_type, entity_id) "
            "VALUES ('semilla', 'concept.created', 'concept', '1')"
        )
    )

    with pytest.raises(DataError):
        conn.execute(
            text(
                "INSERT INTO audit_log (user_id, action, entity_type, entity_id, ip) "
                "VALUES ('x', 'concept.created', 'concept', '1', 'no-es-ip')"
            )
        )


def test_existen_los_indices(conn: Connection) -> None:
    names = set(
        conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'audit_log'")
        ).scalars()
    )

    assert {"audit_log_created_id", "audit_log_entity", "audit_log_action"} <= names
