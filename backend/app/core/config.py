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

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from app.domain.sources import parse_sources

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
# - GDELT: una petición cada 5 s. No está en la página de DOC 2.0, pero lo
#   dice el propio GDELT en su respuesta 429: "Please limit requests to one
#   every 5 seconds" (medido el 16/10/2026).
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
# Páginas de Google News por consulta (10 notas cada una, 1 crédito cada una;
# se piden solo mientras vengan llenas). Medido el 21/10/2026 (ADR-0019).
_DEFAULT_SEARCHAPI_MAX_PAGES = 3
_MAX_SEARCHAPI_PAGES = 10

# Ingesta al índice local (ADR-0013):
# - 90 días de notas, igual que la ventana que cubre la API de GDELT.
_DEFAULT_NEWS_INDEX_RETENTION_DAYS = 90
# - GDELT publica un GKG cada 15 minutos; correr más seguido no trae nada nuevo.
_DEFAULT_INGEST_INTERVAL_MINUTES = 15
# - Frases del cuerpo (ngramas, ADR-0014): 30 días; son lo que más ocupa.
_DEFAULT_NEWS_BODY_RETENTION_DAYS = 30
# - Ngramas: cada corrida revisa los últimos 35 minutos (el intervalo de 15
#   más margen por retrasos de GDELT) y deja los 3 más recientes para la
#   siguiente: GDELT recomienda pedir el archivo de hace unos minutos.
_DEFAULT_NGRAMS_LOOKBACK_MINUTES = 35
_DEFAULT_NGRAMS_DELAY_MINUTES = 3

# Pipeline de búsqueda (F4, ADR-0015):
# - 15 s por página: en la muestra real del 16/10/2026 la más lenta tardó 1.6 s.
_DEFAULT_EXTRACTION_TIMEOUT_SECONDS = 15.0
# - 4 páginas a la vez: rápido sin saturar a un mismo medio.
_DEFAULT_EXTRACTION_CONCURRENCY = 4
# - El texto extraído se borra a los 30 días (solo sirve para procesar).
_DEFAULT_ARTICLE_TEXT_RETENTION_DAYS = 30
# - IA (ADR-0016): OpenAI gpt-6-luna por defecto; Gemini 2.5 Flash elegible.
#   Precios por millón de tokens: OpenAI al 17/10/2026
#   (https://developers.openai.com/api/docs/pricing): 0.10 entrada, 0.50
#   salida; Gemini al 16/10/2026 (https://ai.google.dev/gemini-api/docs/pricing):
#   0.30 entrada, 2.50 salida.
_DEFAULT_LLM_PROVIDER: Literal["openai", "gemini"] = "openai"
_DEFAULT_OPENAI_MODEL = "gpt-6-luna"
_DEFAULT_OPENAI_PRICE_INPUT = 0.10
_DEFAULT_OPENAI_PRICE_OUTPUT = 0.50
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_DEFAULT_GEMINI_PRICE_INPUT = 0.30
_DEFAULT_GEMINI_PRICE_OUTPUT = 2.50
# - 60 s por nota: una respuesta de ~300 tokens tarda unos segundos; el margen
#   cubre horas pico.
_DEFAULT_LLM_TIMEOUT_SECONDS = 60.0
# - 4 notas a la vez: rápido sin tocar los límites por minuto del nivel gratis.
_DEFAULT_LLM_CONCURRENCY = 4
# - Tope por búsqueda (ADR-0015): ~0.20 USD como máximo.
_DEFAULT_LLM_MAX_ARTICLES = 150
# BrowserWork (ADR-0028). Su API acepta de 1 a 10 páginas (SearchRequest de
# BrowserWork); 240 s < CAPTCHA_WAIT_S (600 s) de su servidor; preguntar cada
# 3 s no carga su API y avisa pronto.
_DEFAULT_BROWSERWORK_PAGES = 1
_MAX_BROWSERWORK_PAGES = 10
_DEFAULT_BROWSERWORK_TIMEOUT_SECONDS = 240.0
_DEFAULT_BROWSERWORK_POLL_SECONDS = 3.0
# - Confianza mínima de la ubicación principal (§11).
_DEFAULT_GEO_MIN_CONFIDENCE = 0.6

# Versión de la API que se reporta en /health y en OpenAPI. Sube con cada fase
# (CLAUDE.md §4.3: tag v0.<N>.0 al cerrar la fase N).
APP_VERSION = "0.7.0"


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
    searchapi_max_pages: int = Field(
        default=_DEFAULT_SEARCHAPI_MAX_PAGES, ge=1, le=_MAX_SEARCHAPI_PAGES
    )
    # Google News RSS: activado por defecto desde el dictamen de la Dirección del
    # 24/10/2026 (ADR-0021, sustituye al 0011). NEWS_RSS_ENABLED=false lo apaga.
    news_rss_enabled: bool = True
    # Fuentes encendidas por defecto en la búsqueda manual (switches, F12.2,
    # ADR-0027). SearchApi va apagado: en la medición del 25/10/2026, 27 de sus
    # 30 notas ya venían en el RSS (decisión de Benji). El analista lo enciende.
    manual_default_sources: str = "google_news_rss,indice_local"
    # BrowserWork (ADR-0028): servicio del jefe de Benji que busca en Bing y en
    # Google 2 con un Chrome real. Sin dirección no se ofrece. No lleva llave.
    browserwork_base_url: str | None = None
    # 1 página (unas 10 notas por motor): su navegador atiende una búsqueda a
    # la vez para todos sus usuarios, así que se pide lo mínimo.
    browserwork_pages: int = Field(
        default=_DEFAULT_BROWSERWORK_PAGES, ge=1, le=_MAX_BROWSERWORK_PAGES
    )
    # Tope de espera por búsqueda: menos que los 600 s que BrowserWork espera
    # a que una persona resuelva un captcha, para no colgar la búsqueda.
    browserwork_timeout_seconds: float = Field(default=_DEFAULT_BROWSERWORK_TIMEOUT_SECONDS, gt=0)
    browserwork_poll_seconds: float = Field(default=_DEFAULT_BROWSERWORK_POLL_SECONDS, gt=0)
    # GDELT: desactivado por defecto mientras responda 429 de forma persistente
    # (ADR-0012). Se propone reactivarlo con evidencia: make gdelt-diagnostico.
    gdelt_enabled: bool = False

    # --- Ingesta periódica al índice local (ADR-0013) ---
    # Archivos GKG de GDELT (solo títulos): apagados por defecto desde que los
    # ngramas funcionan (ADR-0014), para no sumar ~760 MB de descarga al día.
    gdelt_gkg_enabled: bool = False
    # RSS de medios: encendidos por Benji el 16/10/2026 (La Jornada, El Universal,
    # Infobae México). Cada medio se activa por separado en fuentes/medios_rss.csv.
    media_rss_enabled: bool = True
    news_index_retention_days: int = Field(default=_DEFAULT_NEWS_INDEX_RETENTION_DAYS, ge=1)
    ingest_interval_minutes: int = Field(default=_DEFAULT_INGEST_INTERVAL_MINUTES, ge=1)
    # Ngramas de GDELT (ADR-0014): texto completo, ~1 GB de descarga al día.
    # Encendidos por Benji el 16/10/2026 tras ver 5 ejemplos y el consumo medido.
    gdelt_ngrams_enabled: bool = True
    news_body_retention_days: int = Field(default=_DEFAULT_NEWS_BODY_RETENTION_DAYS, ge=1)
    ngrams_lookback_minutes: int = Field(default=_DEFAULT_NGRAMS_LOOKBACK_MINUTES, ge=1)
    ngrams_delay_minutes: int = Field(default=_DEFAULT_NGRAMS_DELAY_MINUTES, ge=0)

    # --- Pipeline de búsqueda (F4, ADR-0015) ---
    extraction_timeout_seconds: float = Field(default=_DEFAULT_EXTRACTION_TIMEOUT_SECONDS, gt=0)
    extraction_concurrency: int = Field(default=_DEFAULT_EXTRACTION_CONCURRENCY, ge=1)
    article_text_retention_days: int = Field(default=_DEFAULT_ARTICLE_TEXT_RETENTION_DAYS, ge=1)
    # IA (§10, ADR-0015 y ADR-0016). Sin la llave del proveedor elegido, las
    # notas no se enriquecen y la búsqueda lo avisa.
    llm_provider: Literal["openai", "gemini"] = _DEFAULT_LLM_PROVIDER
    openai_api_key: SecretStr | None = None
    openai_model: str = _DEFAULT_OPENAI_MODEL
    openai_price_input_per_million: float = Field(default=_DEFAULT_OPENAI_PRICE_INPUT, ge=0)
    openai_price_output_per_million: float = Field(default=_DEFAULT_OPENAI_PRICE_OUTPUT, ge=0)
    gemini_api_key: SecretStr | None = None
    gemini_model: str = _DEFAULT_GEMINI_MODEL
    gemini_price_input_per_million: float = Field(default=_DEFAULT_GEMINI_PRICE_INPUT, ge=0)
    gemini_price_output_per_million: float = Field(default=_DEFAULT_GEMINI_PRICE_OUTPUT, ge=0)
    llm_timeout_seconds: float = Field(default=_DEFAULT_LLM_TIMEOUT_SECONDS, gt=0)
    llm_concurrency: int = Field(default=_DEFAULT_LLM_CONCURRENCY, ge=1)
    llm_max_articles_per_search: int = Field(default=_DEFAULT_LLM_MAX_ARTICLES, ge=1)
    geo_min_confidence: float = Field(default=_DEFAULT_GEO_MIN_CONFIDENCE, ge=0, le=1)

    @field_validator("manual_default_sources")
    @classmethod
    def _known_sources(cls, value: str) -> str:
        """Falla al arrancar si ``MANUAL_DEFAULT_SOURCES`` nombra una fuente que no existe."""
        parse_sources(value)
        return value

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
