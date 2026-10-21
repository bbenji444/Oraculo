"""Migración 0021: nombres de entidades sin comillas (Fase 9.5, decisión D1).

La 9.4 guardó ``label_norm`` y ``alias_norm`` con las comillas del medio
("JULIAN “N”"), así que el mismo nombre quedaba en sugerencias distintas. La
migración los recalcula y junta los alias que quedan repetidos. Se prueba
bajando a la 0020, sembrando nombres como los dejó la 9.4 y subiendo.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.core.config import Settings
from app.domain.entity_resolution import entity_name_norm

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def at_0020(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Iterator[tuple[Config, Engine]]:
    monkeypatch.setenv("ALEMBIC_TARGET", "test")
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "head")
    command.downgrade(config, "0020")
    engine = create_engine(settings.database_url(test=True))
    yield config, engine
    command.upgrade(config, "head")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM entities WHERE canonical_label LIKE 'Migración%'"))
    engine.dispose()


def test_la_0021_quita_las_comillas_y_junta_alias_repetidos(
    at_0020: tuple[Config, Engine],
) -> None:
    config, engine = at_0020
    with engine.begin() as conn:
        entity = conn.execute(
            text(
                "INSERT INTO entities (type, canonical_label, label_norm) "
                "VALUES ('person', 'Migración “N”', 'MIGRACION “N”') RETURNING id"
            )
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO entity_aliases (entity_id, alias, alias_norm) VALUES "
                "(:e, 'Migración ''N''', 'MIGRACION ''N'''), "
                "(:e, 'Migración «N»', 'MIGRACION «N»'), "
                "(:e, 'Mig  “Equis”', 'MIG “EQUIS”')"
            ),
            {"e": entity},
        )

    command.upgrade(config, "0021")

    with engine.connect() as conn:
        label_norm = conn.execute(
            text("SELECT label_norm FROM entities WHERE id = :e"), {"e": entity}
        ).scalar_one()
        aliases = conn.execute(
            text("SELECT alias, alias_norm FROM entity_aliases WHERE entity_id = :e ORDER BY id"),
            {"e": entity},
        ).all()
    # La migración escribe lo mismo que el código (no lo importa: aquí se compara).
    assert label_norm == entity_name_norm("Migración “N”") == "MIGRACION N"
    # Los dos alias que quedaron iguales se juntan en el más antiguo.
    assert [tuple(row) for row in aliases] == [
        ("Migración 'N'", "MIGRACION N"),
        ("Mig  “Equis”", "MIG EQUIS"),
    ]
