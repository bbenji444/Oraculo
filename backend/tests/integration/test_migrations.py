"""Migraciones de Alembic aplicadas sobre la base de pruebas."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import Settings

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_migraciones_suben_bajan_y_vuelven_a_subir_en_la_base_de_pruebas(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setenv("ALEMBIC_TARGET", "test")
    config = Config(str(BACKEND_DIR / "alembic.ini"))

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(settings.database_url(test=True))
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert version == "0001"
