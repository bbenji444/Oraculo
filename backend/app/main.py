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
from datetime import UTC, datetime

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.delivery.factory import build_connector, build_senders
from app.adapters.health.app_probe import AppHealthProbe
from app.adapters.health.celery_probe import CeleryWorkerHealthProbe
from app.adapters.health.postgres_probe import PostgresHealthProbe
from app.adapters.health.redis_probe import RedisHealthProbe
from app.adapters.llm.factory import (
    MissingLLMKeyError,
    SummarizerSetup,
    build_summarizer,
    llm_info,
)
from app.adapters.persistence.case_graph_repository import PostgresCaseGraphRepository
from app.adapters.persistence.cases_repository import PostgresCaseRepository
from app.adapters.persistence.categories_repository import PostgresCategoryStore
from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.adapters.persistence.deliveries_repository import PostgresDeliveryStore
from app.adapters.persistence.delivery_reports import PostgresRunReports
from app.adapters.persistence.entities_repository import PostgresEntityRepository
from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.persistence.relationships_repository import PostgresRelationshipRepository
from app.adapters.persistence.reports_repository import PostgresReportStore
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.adapters.queue.celery_queue import CeleryEntityQueue, CelerySearchQueue
from app.adapters.reports.render import ReportRenderer
from app.adapters.reports.static_map import PostgisStaticMap
from app.api.errors import register_error_handlers
from app.api.v1 import OPENAPI_TAGS, api_router
from app.api.v1.deliveries import OverviewOut, SourceOut
from app.application.use_cases.check_health import CheckSystemHealth
from app.application.use_cases.deliveries import SendDeliveries
from app.application.use_cases.entities import QueueExtraction
from app.application.use_cases.plan_search import PlanSearch
from app.application.use_cases.reports import BuildReport, ExportSearch, LLMPrices
from app.core.config import APP_VERSION, Settings, get_settings
from app.core.logging import configure_logging
from app.domain.deliveries import SOURCES
from app.domain.schedule import parse_run_hours
from app.domain.sources import parse_sources
from app.worker.celery_app import create_celery_app
from app.worker.search_jobs import build_providers

API_PREFIX = "/api/v1"

# El ping al worker usa la mitad del tiempo total por componente para que,
# si nadie responde, el mensaje sea "ningún worker respondió" y no un timeout.
_WORKER_PING_FRACTION = 0.5


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _summarizer(settings: Settings) -> SummarizerSetup | None:
    # Sin la llave de la IA, el reporte sale igual, con un aviso en lugar del
    # resumen ejecutivo (ADR-0018).
    try:
        return build_summarizer(settings)
    except MissingLLMKeyError:
        return None


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
        # Casos de investigación (Fase 9.3): acceso por caso y bitácora.
        app.state.case_repository = PostgresCaseRepository(engine)
        app.state.dev_user = settings.dev_user
        # Entidades de los casos (Fase 9.4): la IA lee cada nota nueva en el worker.
        app.state.entity_repository = PostgresEntityRepository(engine)
        app.state.extraction_queue = QueueExtraction(
            app.state.entity_repository, CeleryEntityQueue(celery_app)
        )
        # Vínculos de los casos (Fase 9.5): la coocurrencia se calcula al leer.
        app.state.relationship_repository = PostgresRelationshipRepository(engine)
        # Muro de los casos sobre el globo (Fase 9.6).
        app.state.case_graph_repository = PostgresCaseGraphRepository(engine)
        app.state.case_max_visible_nodes = settings.case_max_visible_nodes
        info = llm_info(settings)
        app.state.llm_prices = LLMPrices(
            info.provider, info.price_input_per_million, info.price_output_per_million
        )
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
            default_sources=parse_sources(settings.manual_default_sources),
        )
        app.state.search_store = PostgresSearchStore(engine)
        # Catálogo de categorías de noticias (F12.4, ADR-0029).
        app.state.category_store = PostgresCategoryStore(engine)
        app.state.article_store = PostgresArticleStore(engine)
        app.state.search_queue = CelerySearchQueue(celery_app)
        app.state.max_queries_per_search = settings.max_queries_per_search
        # Reportes (F7, ADR-0018): resumen ejecutivo, mapa estático y archivos.
        report_store = PostgresReportStore(engine)
        summarizer = _summarizer(settings)
        app.state.report_builder = BuildReport(
            searches=app.state.search_store,
            articles=app.state.article_store,
            regions=app.state.region_repository,
            store=report_store,
            static_map=PostgisStaticMap(engine),
            summarizer=summarizer.summarizer if summarizer else None,
            prices=(
                LLMPrices(
                    summarizer.provider,
                    summarizer.price_input_per_million,
                    summarizer.price_output_per_million,
                )
                if summarizer
                else None
            ),
            clock=_utc_now,
            previous_runs=app.state.search_store,
        )
        app.state.search_exporter = ExportSearch(
            app.state.search_store,
            app.state.article_store,
            app.state.region_repository,
            report_store,
            _utc_now,
        )
        app.state.report_documents = ReportRenderer()
        # Envíos (F12.11, ADR-0039).
        delivery_store = PostgresDeliveryStore(engine)
        delivery_reports = PostgresRunReports(engine)
        app.state.delivery_store = delivery_store
        app.state.delivery_reports = delivery_reports
        app.state.delivery_connector = build_connector(settings)
        app.state.delivery_sender = SendDeliveries(
            delivery_store, delivery_reports, build_senders(settings)
        )
        app.state.delivery_overview = OverviewOut(
            enabled=settings.deliveries_enabled,
            email_configured=settings.composio_api_key is not None,
            whatsapp_available=False,
            sources=[SourceOut(id=k, label=v) for k, v in SOURCES.items()],
            run_hours=sorted(parse_run_hours(settings.automatic_run_hours)),
            run_times=[
                f"{h:02d}:00" for h in sorted(parse_run_hours(settings.automatic_run_hours))
            ],
        )
        try:
            yield
        finally:
            if summarizer:
                await summarizer.summarizer.aclose()
            await redis_client.aclose()
            await engine.dispose()

    app = FastAPI(
        title="Monitor de Noticias",
        description=(
            "API del monitor de noticias geolocalizadas sobre México. Errores con la forma "
            '{"error": {"code", "message", "details"}} y mensajes en español; '
            "listas con paginación por cursor. Ejemplos con curl en docs/api.md."
        ),
        openapi_tags=OPENAPI_TAGS,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
