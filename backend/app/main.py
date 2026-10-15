"""Punto de entrada de la API FastAPI.

Arma la aplicación: configura logs, crea las conexiones compartidas (base de
datos, Redis, Celery) al arrancar y las cierra al apagar, y conecta los
adaptadores con los casos de uso (raíz de composición).

Se arranca con ``uvicorn app.main:app`` (lo hace ``make up``).
No hace: no contiene lógica de negocio ni rutas propias; las rutas están en
``app.api.v1``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.health.app_probe import AppHealthProbe
from app.adapters.health.celery_probe import CeleryWorkerHealthProbe
from app.adapters.health.postgres_probe import PostgresHealthProbe
from app.adapters.health.redis_probe import RedisHealthProbe
from app.api.v1 import api_router
from app.application.use_cases.check_health import CheckSystemHealth
from app.core.config import APP_VERSION, Settings, get_settings
from app.core.logging import configure_logging
from app.worker.celery_app import create_celery_app

API_PREFIX = "/api/v1"

# El ping al worker usa la mitad del tiempo total por componente para que,
# si nadie responde, el mensaje sea "ningún worker respondió" y no un timeout.
_WORKER_PING_FRACTION = 0.5


def create_app(settings: Settings | None = None) -> FastAPI:
    """Crea la aplicación FastAPI.

    Args:
        settings: Configuración a usar. Si es ``None`` se lee del entorno.

    Returns:
        La aplicación lista para uvicorn.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # pool_pre_ping descarta conexiones muertas (por ejemplo, si
        # PostgreSQL se reinició) antes de usarlas.
        engine = create_async_engine(settings.database_url(), pool_pre_ping=True)
        redis_client = Redis.from_url(
            settings.redis_url,
            socket_timeout=settings.health_check_timeout_seconds,
            socket_connect_timeout=settings.health_check_timeout_seconds,
        )
        celery_app = create_celery_app(settings)
        app.state.check_health = CheckSystemHealth(
            probes=[
                AppHealthProbe(version=APP_VERSION, environment=settings.app_env),
                PostgresHealthProbe(engine),
                RedisHealthProbe(redis_client),
                CeleryWorkerHealthProbe(
                    celery_app,
                    reply_timeout_seconds=settings.health_check_timeout_seconds
                    * _WORKER_PING_FRACTION,
                ),
            ],
            timeout_seconds=settings.health_check_timeout_seconds,
        )
        try:
            yield
        finally:
            await redis_client.aclose()
            await engine.dispose()

    app = FastAPI(
        title="Monitor de Noticias",
        description="API del monitor de noticias geolocalizadas sobre México.",
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
