"""Arma y corre el pipeline de una búsqueda con piezas reales (especificación §9).

Es el punto donde se juntan los proveedores, la base, Redis, el extractor y
la IA elegida (``LLM_PROVIDER``). Lo usan la tarea de Celery
(``app.worker.tasks.run_search``) y el comando ``make buscar --aqui``, para
que los dos hagan exactamente lo mismo.

Proveedores de una búsqueda (plan de F4): SearchApi (con créditos, si hay
llave) y el índice local (gratis). La API de GDELT y Google News RSS
siguen apagados (ADR-0011 y ADR-0012).

No hace: no decide cuándo correr ni muestra nada.
"""

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.adapters.cache.redis_query_cache import RedisQueryCache
from app.adapters.extraction.trafilatura_extractor import build_extractor
from app.adapters.llm.factory import LLMSetup, build_llm
from app.adapters.persistence.gazetteer_repository import PostgresGazetteer
from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.adapters.persistence.stories_repository import PostgresStoryStore
from app.adapters.providers.factory import build_provider
from app.adapters.text.similarity import title_similarity, title_token_similarity
from app.application.ports.providers import NewsProviderPort
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionLimits
from app.application.use_cases.extraction import ExtractTexts
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.run_search import PipelineLimits, RunSearch, SearchReport
from app.application.use_cases.stories import GroupStories
from app.core.config import Settings
from app.domain.queries import Provider

logger = logging.getLogger(__name__)

# Proveedores de una búsqueda, en orden (plan de F4). Google News RSS entra
# desde el ADR-0021; si NEWS_RSS_ENABLED=false se arma igual pero dice que no
# está configurado y no recibe consultas.
SEARCH_PROVIDERS = (
    Provider.SEARCHAPI,
    Provider.GOOGLE_NEWS_RSS,
    Provider.LOCAL_INDEX,
    # Sin BROWSERWORK_BASE_URL dicen que no están configurados (ADR-0028).
    Provider.BROWSERWORK_BING,
    Provider.BROWSERWORK_GOOGLE2,
)


def build_providers(settings: Settings, engine: AsyncEngine) -> dict[Provider, NewsProviderPort]:
    """Adaptadores de los proveedores de una búsqueda.

    Args:
        settings: Configuración.
        engine: Conexión a la base (la usa el índice local).

    Returns:
        Un adaptador por proveedor; SearchApi sin llave dice que no está
        configurado y no se planea.
    """
    return {p: build_provider(p, settings, engine) for p in SEARCH_PROVIDERS}


@asynccontextmanager
async def search_pipeline(
    settings: Settings,
    log_progress: Callable[[UUID, Mapping[str, object]], None] | None = None,
) -> AsyncIterator[tuple[RunSearch, LLMSetup, AsyncEngine]]:
    """Abre las conexiones, arma ``RunSearch`` y las cierra al salir.

    Args:
        settings: Configuración.
        log_progress: Aviso de avance (el comando lo muestra en pantalla).

    Yields:
        El caso de uso, la IA elegida (con sus precios) y el engine.

    Raises:
        MissingLLMKeyError: Si falta la llave de la IA elegida.
    """
    llm = build_llm(settings)
    engine = create_async_engine(settings.database_url(), pool_pre_ping=True)
    redis = Redis.from_url(settings.redis_url)
    extractor = build_extractor(settings)
    providers = build_providers(settings, engine)
    gazetteer = PostgresGazetteer(engine)
    try:
        executor = ExecuteQueries(
            providers,
            RedisQueryCache(redis),
            PostgresProviderQueryLog(engine),
            ExecutionLimits(
                settings.max_queries_per_search,
                settings.query_cache_ttl_hours,
                {Provider.SEARCHAPI: settings.searchapi_monthly_credit_limit},
            ),
        )
        use_case = RunSearch(
            searches=PostgresSearchStore(engine),
            articles=PostgresArticleStore(engine),
            regions=PostgresRegionRepository(engine),
            gazetteer=gazetteer,
            providers=providers,
            executor=executor,
            extractor=ExtractTexts(extractor, settings.extraction_concurrency),
            llm=llm.llm,
            geocoder=GeocodeMentions(gazetteer, settings.geo_min_confidence),
            similarity=title_similarity,
            stories=GroupStories(
                PostgresStoryStore(engine), title_similarity, title_token_similarity
            ),
            limits=PipelineLimits(
                settings.llm_max_articles_per_search,
                settings.llm_concurrency,
                llm.price_input_per_million,
                llm.price_output_per_million,
            ),
            **({"log_progress": log_progress} if log_progress else {}),
        )
        yield use_case, llm, engine
    finally:
        await llm.llm.aclose()
        await extractor.aclose()
        await redis.aclose()
        await engine.dispose()


async def run_search_job(
    settings: Settings,
    search_id: UUID,
    log_progress: Callable[[UUID, Mapping[str, object]], None] | None = None,
) -> SearchReport:
    """Corre una búsqueda guardada. Si algo inesperado truena, la deja en ``failed``.

    Args:
        settings: Configuración.
        search_id: Búsqueda en ``pending``.
        log_progress: Aviso de avance.

    Returns:
        El resumen de la búsqueda.

    Raises:
        Exception: El error inesperado, después de marcar la búsqueda como
            ``failed`` (para que nunca quede "corriendo" para siempre).
    """
    async with search_pipeline(settings, log_progress) as (use_case, _llm, engine):
        try:
            return await use_case.run(search_id)
        except Exception as error:
            # Cualquier error que no sea de una nota (base caída, bug): la
            # búsqueda no puede quedar en "running" para siempre.
            logger.exception("La búsqueda falló", extra={"search_id": str(search_id)})
            await PostgresSearchStore(engine).fail(
                search_id, f"Error inesperado ({type(error).__name__}): {error}"
            )
            raise


async def purge_article_texts(settings: Settings) -> int:
    """Borra los textos extraídos más viejos que ``ARTICLE_TEXT_RETENTION_DAYS`` (ADR-0015).

    Args:
        settings: Configuración.

    Returns:
        Cuántos textos se borraron.
    """
    engine = create_async_engine(settings.database_url())
    try:
        return await PostgresArticleStore(engine).purge_texts(settings.article_text_retention_days)
    finally:
        await engine.dispose()
