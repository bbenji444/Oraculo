"""Lectura de configuración desde variables de entorno."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE_ENV = {
    "POSTGRES_HOST": "db.local",
    "POSTGRES_USER": "monitor",
    "POSTGRES_PASSWORD": "p@ss/word",
    "POSTGRES_DB": "monitor_noticias",
    "POSTGRES_TEST_DB": "monitor_noticias_test",
    "REDIS_URL": "redis://localhost:6379/0",
    "REDIS_TEST_URL": "redis://localhost:6379/15",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def build_settings() -> Settings:
    # _env_file=None: la prueba no debe leer el .env real del desarrollador.
    return Settings(_env_file=None)


def test_lee_variables_de_entorno(env: pytest.MonkeyPatch) -> None:
    settings = build_settings()

    assert settings.postgres_host == "db.local"
    assert settings.postgres_port == 5432
    assert settings.app_env == "development"


def test_la_contrasena_no_aparece_al_imprimir_la_configuracion(env: pytest.MonkeyPatch) -> None:
    settings = build_settings()

    assert "p@ss/word" not in repr(settings)
    assert settings.postgres_password.get_secret_value() == "p@ss/word"


def test_database_url_escapa_caracteres_especiales_de_la_contrasena(
    env: pytest.MonkeyPatch,
) -> None:
    url = build_settings().database_url()

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss/word"
    assert url.database == "monitor_noticias"
    assert "p%40ss%2Fword" in url.render_as_string(hide_password=False)


def test_database_url_de_pruebas_usa_la_base_separada(env: pytest.MonkeyPatch) -> None:
    assert build_settings().database_url(test=True).database == "monitor_noticias_test"


def test_falta_una_variable_obligatoria(env: pytest.MonkeyPatch) -> None:
    env.delenv("POSTGRES_PASSWORD")

    with pytest.raises(ValidationError, match="postgres_password"):
        build_settings()


def test_timeout_de_health_debe_ser_positivo(env: pytest.MonkeyPatch) -> None:
    env.setenv("HEALTH_CHECK_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValidationError, match="health_check_timeout_seconds"):
        build_settings()
