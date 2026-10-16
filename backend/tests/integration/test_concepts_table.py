"""Reglas de la tabla concepts que garantiza la propia base de datos."""

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
        # Cada prueba deshace sus cambios: la base de pruebas queda limpia.
        yield connection
        transaction.rollback()
    engine.dispose()


def insert(
    conn: Connection,
    name: str = "Secuestro",
    *,
    keywords: str = "ARRAY['secuestro']",
    color: str = "#E74C3C",
) -> int:
    row_id: int = conn.execute(
        text(
            f"""
            INSERT INTO concepts (name, name_norm, keywords, color, created_by)
            VALUES (:name, upper(:name), {keywords}, :color, 'prueba')
            RETURNING id
            """  # noqa: S608 — solo constantes de esta prueba se interpolan, nunca datos externos
        ),
        {"name": name, "color": color},
    ).scalar_one()
    return row_id


def test_valores_por_defecto(conn: Connection) -> None:
    concept_id = insert(conn)

    row = conn.execute(
        text(
            "SELECT description, exclude_terms, is_active, deleted_at FROM concepts WHERE id = :id"
        ),
        {"id": concept_id},
    ).one()

    assert tuple(row) == ("", [], True, None)


def test_nombre_repetido_entre_vigentes_se_rechaza(conn: Connection) -> None:
    insert(conn)

    with pytest.raises(IntegrityError, match="concepts_name_norm_active_key"):
        insert(conn)


def test_un_concepto_borrado_libera_su_nombre(conn: Connection) -> None:
    concept_id = insert(conn)
    conn.execute(text("UPDATE concepts SET deleted_at = now() WHERE id = :id"), {"id": concept_id})

    insert(conn)


def test_sin_palabras_clave_se_rechaza(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="concepts_has_keywords"):
        insert(conn, keywords="ARRAY[]::text[]")


@pytest.mark.parametrize("color", ["#e74c3c", "E74C3C", "#E74C3", "rojo"])
def test_color_invalido_se_rechaza(conn: Connection, color: str) -> None:
    with pytest.raises(IntegrityError, match="concepts_color_hex"):
        insert(conn, color=color)


def test_updated_at_lo_pone_el_disparador(conn: Connection) -> None:
    concept_id = insert(conn)

    conn.execute(
        text("UPDATE concepts SET updated_at = '2000-01-01T00:00:00Z' WHERE id = :id"),
        {"id": concept_id},
    )
    updated_at, now = conn.execute(
        text("SELECT updated_at, now() FROM concepts WHERE id = :id"), {"id": concept_id}
    ).one()

    assert updated_at == now


def test_existen_los_indices(conn: Connection) -> None:
    names = set(
        conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'concepts'")
        ).scalars()
    )

    assert {"concepts_name_norm_active_key", "concepts_name_id", "concepts_active_name_id"} <= names
