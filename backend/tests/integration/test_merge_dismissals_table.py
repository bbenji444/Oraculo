"""Reglas de la migración 0022 que garantiza la base (Fase 9.5, decisión D3).

Un «No son la misma» se guarda una vez por caso y par, con el id menor
primero, y desaparece si se borra el caso o una de las entidades.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from tests.integration.test_investigation_tables import new_case, new_entity

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]

_DISMISS = text(
    "INSERT INTO entity_merge_dismissals (case_id, entity_low, entity_high, dismissed_by) "
    "VALUES (:case, :low, :high, 'benji')"
)
_COUNT = text("SELECT count(*) FROM entity_merge_dismissals WHERE case_id = :case")


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


def test_un_par_se_descarta_una_sola_vez_y_con_el_menor_primero(conn: Connection) -> None:
    case = new_case(conn)
    low, high = sorted((new_entity(conn), new_entity(conn, label="Eduardo “N”")))

    conn.execute(_DISMISS, {"case": case, "low": low, "high": high})

    with pytest.raises(IntegrityError, match="dismissals_ordered"), conn.begin_nested():
        conn.execute(_DISMISS, {"case": case, "low": high, "high": low})
    with pytest.raises(IntegrityError, match="dismissals_pkey"), conn.begin_nested():
        conn.execute(_DISMISS, {"case": case, "low": low, "high": high})


def test_borrar_una_entidad_o_el_caso_borra_el_descarte(conn: Connection) -> None:
    case = new_case(conn)
    first, second, third = (new_entity(conn, label=f"Persona {n}") for n in range(3))
    conn.execute(_DISMISS, {"case": case, "low": first, "high": second})
    conn.execute(_DISMISS, {"case": case, "low": first, "high": third})

    conn.execute(text("DELETE FROM entities WHERE id = :e"), {"e": second})
    assert conn.execute(_COUNT, {"case": case}).scalar_one() == 1
    conn.execute(text("DELETE FROM cases WHERE id = :c"), {"c": case})
    assert conn.execute(_COUNT, {"case": case}).scalar_one() == 0
