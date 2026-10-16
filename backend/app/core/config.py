"""Configuración de la aplicación, leída solo de variables de entorno.

Lee las variables del entorno y, si existe, del archivo ``.env`` en la raíz
del repositorio (ver ``.env.example`` para la lista documentada). Lo usan
``app.main``, el worker y las migraciones de Alembic.

No hace: no tiene valores secretos por defecto. Si falta una variable
obligatoria, la aplicación no arranca y pydantic dice cuál falta.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# backend/app/core/config.py → la raíz del repositorio está 3 niveles arriba.
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Tiempo máximo por componente en /health. 2 s es suficiente para servicios
# locales y evita que el endpoint se cuelgue si uno no responde.
_DEFAULT_HEALTH_TIMEOUT_SECONDS = 2.0

# Puerto estándar de PostgreSQL.
_DEFAULT_POSTGRES_PORT = 5432

# Carpeta de trabajo del pipeline de geodatos, en el disco de Linux. GDAL no
# lee directamente de /mnt/d: en WSL con kernel 5.10 llegó a recibir bytes
# basura de un archivo que Python y `head` leían bien (ADR-0008).
_DEFAULT_GEODATA_WORK_DIR = Path.home() / ".cache" / "monitor-noticias" / "geodata"

# Nombre del usuario de desarrollo en la bitácora de auditoría.
_DEFAULT_DEV_USER = "desarrollo"

# Proveedores de noticias (plan aprobado de F3):
# - 20 s por petición; SearchApi 30 s porque link=resolved sigue redirecciones.
_DEFAULT_PROVIDER_TIMEOUT_SECONDS = 20.0
_DEFAULT_SEARCHAPI_TIMEOUT_SECONDS = 30.0
# - 3 intentos en total (esperas de 1 s y 2 s entre ellos).
_DEFAULT_PROVIDER_MAX_ATTEMPTS = 3
# - 2 peticiones simultáneas por proveedor: suficiente para pocas consultas
#   por búsqueda sin parecer un ataque.
_DEFAULT_PROVIDER_MAX_CONCURRENCY = 2
# - GDELT: una petición cada 5 s. VERIFICAR: cifra que circula en la
#   comunidad, no documentada en la página de DOC 2.0.
_DEFAULT_GDELT_MIN_INTERVAL_SECONDS = 5.0
# - GDELT: tras un 429, esperar al menos 15 s antes de reintentar. Medido el
#   16/10/2026: reintentos a 1-5 s recibían 429 de nuevo (plan aprobado).
_DEFAULT_GDELT_RATE_LIMIT_WAIT_SECONDS = 15.0
# - Especificación §7.2: máximo 10 consultas por búsqueda; caché de 6 h.
_DEFAULT_MAX_QUERIES_PER_SEARCH = 10
_DEFAULT_QUERY_CACHE_TTL_HOURS = 6.0
# - Tope mensual de créditos de SearchApi: las 100 búsquedas de la prueba
#   gratuita. Red de seguridad contra gastos por error.
_DEFAULT_SEARCHAPI_MONTHLY_LIMIT = 100

# Versión de la API que se reporta en /health y en OpenAPI. Sube con cada fase
# (CLAUDE.md §4.3: tag v0.<N>.0 al cerrar la fase N).
APP_VERSION = "0.2.0"


class Settings(BaseSettings):
    """Variables de entorno del backend.

    Cada atributo corresponde a una variable en mayúsculas (``postgres_host``
    → ``POSTGRES_HOST``). La descripción de cada una está en ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    postgres_host: str
    postgres_port: int = _DEFAULT_POSTGRES_PORT
    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str
    postgres_test_db: str

    redis_url: str
    redis_test_url: str

    health_check_timeout_seconds: float = Field(default=_DEFAULT_HEALTH_TIMEOUT_SECONDS, gt=0)

    geodata_work_dir: Path = _DEFAULT_GEODATA_WORK_DIR

    # Usuario fijo que firma los cambios en la bitácora hasta que F8 agregue
    # autenticación (especificación §16).
    dev_user: str = Field(default=_DEFAULT_DEV_USER, min_length=1)

    # --- Proveedores de noticias (F3, especificación §7.2 y §8) ---
    # Sin llave, SearchApi se salta con un aviso; GDELT y RSS no la necesitan.
    searchapi_api_key: SecretStr | None = None
    provider_timeout_seconds: float = Field(default=_DEFAULT_PROVIDER_TIMEOUT_SECONDS, gt=0)
    searchapi_timeout_seconds: float = Field(default=_DEFAULT_SEARCHAPI_TIMEOUT_SECONDS, gt=0)
    provider_max_attempts: int = Field(default=_DEFAULT_PROVIDER_MAX_ATTEMPTS, ge=1)
    provider_max_concurrency: int = Field(default=_DEFAULT_PROVIDER_MAX_CONCURRENCY, ge=1)
    gdelt_min_interval_seconds: float = Field(default=_DEFAULT_GDELT_MIN_INTERVAL_SECONDS, ge=0)
    gdelt_rate_limit_wait_seconds: float = Field(
        default=_DEFAULT_GDELT_RATE_LIMIT_WAIT_SECONDS, ge=0
    )
    max_queries_per_search: int = Field(default=_DEFAULT_MAX_QUERIES_PER_SEARCH, ge=1)
    query_cache_ttl_hours: float = Field(default=_DEFAULT_QUERY_CACHE_TTL_HOURS, ge=0)
    searchapi_monthly_credit_limit: int = Field(default=_DEFAULT_SEARCHAPI_MONTHLY_LIMIT, ge=0)
    # Google News RSS: desactivado por defecto por sus términos de uso
    # (ADR-0011). Solo se activa a propósito en desarrollo; nunca en producción.
    news_rss_enabled: bool = False
    # GDELT: desactivado por defecto mientras responda 429 de forma persistente
    # (ADR-0012). Se propone reactivarlo con evidencia: make gdelt-diagnostico.
    gdelt_enabled: bool = False

    def database_url(self, *, test: bool = False) -> URL:
        """Construye la URL de conexión de SQLAlchemy con el driver psycopg 3.

        Se arma con ``URL.create`` en lugar de concatenar texto para que una
        contraseña con caracteres especiales (``@``, ``/``) no rompa la URL.

        Args:
            test: Si es ``True``, apunta a la base de pruebas
                (``POSTGRES_TEST_DB``) en lugar de la de desarrollo.

        Returns:
            La URL lista para ``create_engine`` o ``create_async_engine``.
        """
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_test_db if test else self.postgres_db,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la configuración, leída una sola vez por proceso.

    Returns:
        La instancia compartida de ``Settings``.

    Raises:
        pydantic.ValidationError: Si falta una variable obligatoria o tiene
            un valor inválido.
    """
    # pydantic-settings llena los campos obligatorios desde el entorno.
    return Settings()
