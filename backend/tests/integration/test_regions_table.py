"""Reglas de la tabla regions que garantiza la propia base de datos."""

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

# Un cuadrado pequeño cerca del Zócalo, suficiente para probar restricciones.
SQUARE = "ST_Multi(ST_MakeEnvelope(-99.14, 19.43, -99.13, 19.44, 4326))"
POINT = "ST_SetSRID(ST_MakePoint(-99.1332, 19.4326), 4326)"
BBOX = "ARRAY[-99.14, 19.43, -99.13, 19.44]::double precision[]"


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
    conn: Connection, code: str, level: str, *, geom: str | None = SQUARE, bbox: str = BBOX
) -> int:
    row_id: int = conn.execute(
        text(
            f"""
            INSERT INTO regions (level, code, country_code, name, name_norm, display_prefix,
                                 geom, centroid, bbox, source)
            VALUES (:level, :code, 'MEX', 'Peñón', 'PEÑON', 'Localidad',
                    {geom or "NULL"}, {POINT}, {bbox}, 'prueba')
            RETURNING id
            """  # noqa: S608 — solo constantes de esta prueba se interpolan, nunca datos externos
        ),
        {"level": level, "code": code},
    ).scalar_one()
    return row_id


def test_conserva_la_enie_tal_cual(conn: Connection) -> None:
    insert(conn, "TEST1", "locality")

    name, name_norm = conn.execute(
        text("SELECT name, name_norm FROM regions WHERE code = 'TEST1'")
    ).one()

    assert (name, name_norm) == ("Peñón", "PEÑON")


def test_la_clave_es_unica(conn: Connection) -> None:
    insert(conn, "TEST1", "locality")

    with pytest.raises(IntegrityError, match="regions_code_key"):
        insert(conn, "TEST1", "locality")


def test_una_localidad_puede_no_tener_poligono(conn: Connection) -> None:
    insert(conn, "TEST1", "locality", geom=None)


def test_un_estado_sin_poligono_se_rechaza(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="regions_only_localities_without_geom"):
        insert(conn, "TEST1", "state", geom=None)


def test_el_bbox_debe_tener_cuatro_valores(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="regions_bbox_four_values"):
        insert(conn, "TEST1", "locality", bbox="ARRAY[1, 2, 3]::double precision[]")


def test_updated_at_lo_pone_el_disparador_aunque_se_intente_otro_valor(conn: Connection) -> None:
    region_id = insert(conn, "TEST1", "locality")

    # Si el disparador no existiera, quedaría guardado el año 2000.
    conn.execute(
        text("UPDATE regions SET updated_at = '2000-01-01T00:00:00Z' WHERE id = :id"),
        {"id": region_id},
    )
    updated_at, now = conn.execute(
        text("SELECT updated_at, now() FROM regions WHERE id = :id"), {"id": region_id}
    ).one()

    assert updated_at == now


def test_existen_los_indices_de_la_especificacion(conn: Connection) -> None:
    names = set(
        conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'regions'")).scalars()
    )

    assert {
        "regions_geom_gist",
        "regions_centroid_gist",
        "regions_name_norm_trgm",
        "regions_aliases_norm_gin",
        "regions_level_parent",
        "regions_code_prefix",
        "regions_level_name_id",
        "regions_parent_name_id",
    } <= names
