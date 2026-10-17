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

from app.adapters.cache.redis_query_cache import RedisQueryCache
from app.adapters.health.app_probe import AppHealthProbe
from app.adapters.health.celery_probe import CeleryWorkerHealthProbe
from app.adapters.health.postgres_probe import PostgresHealthProbe
from app.adapters.health.redis_probe import RedisHealthProbe
from app.adapters.llm.factory import llm_info
from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.adapters.persistence.news_index_repository import PostgresIndexStats
from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.adapters.providers.local_index import LocalIndexProvider
from app.adapters.queue.celery_queue import CelerySearchQueue
from app.api.errors import register_error_handlers
from app.api.v1 import api_router
from app.application.use_cases.check_health import CheckSystemHealth
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionLimits
from app.application.use_cases.plan_search import PlanSearch
from app.core.config import APP_VERSION, Settings, get_settings
from app.core.logging import configure_logging
from app.domain.queries import Provider
from app.worker.celery_app import create_celery_app
from app.worker.search_jobs import build_providers

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
        app.state.region_repository = PostgresRegionRepository(engine)
        app.state.concept_repository = PostgresConceptRepository(engine)
        app.state.dev_user = settings.dev_user
        # Pestaña temporal "Notas" (ADR-0014): solo el índice local, sin créditos.
        app.state.local_index_executor = ExecuteQueries(
            {Provider.LOCAL_INDEX: LocalIndexProvider(engine)},
            RedisQueryCache(redis_client),
            PostgresProviderQueryLog(engine),
            ExecutionLimits(settings.max_queries_per_search, settings.query_cache_ttl_hours, {}),
        )
        app.state.index_stats = PostgresIndexStats(engine)
        # Búsquedas (F5): la misma planeación que make buscar y la cola del worker.
        concepts = app.state.concept_repository
        app.state.search_planner = PlanSearch(
            concepts=concepts,
            regions=app.state.region_repository,
            providers=build_providers(settings, engine),
            log=PostgresProviderQueryLog(engine),
            llm=llm_info(settings),
            llm_max_articles=settings.llm_max_articles_per_search,
            credits_limit=settings.searchapi_monthly_credit_limit,
        )
        app.state.search_store = PostgresSearchStore(engine)
        app.state.article_store = PostgresArticleStore(engine)
        app.state.search_queue = CelerySearchQueue(celery_app)
        app.state.max_queries_per_search = settings.max_queries_per_search
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
    register_error_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
