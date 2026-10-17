"""Arma los adaptadores de proveedores a partir de la configuración.

Lo usan el comando de prueba y, en F4, el worker. Así la configuración de
tiempos, reintentos y llaves vive en un solo lugar.

No hace: no decide qué proveedores usar en una búsqueda.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.providers.gdelt import GdeltProvider
from app.adapters.providers.google_news_rss import GoogleNewsRssProvider
from app.adapters.providers.http import ProviderHttpClient
from app.adapters.providers.local_index import LocalIndexProvider
from app.adapters.providers.searchapi import SearchApiProvider
from app.application.ports.providers import NewsProviderPort
from app.core.config import Settings
from app.domain.queries import Provider

logger = logging.getLogger(__name__)


def build_gdelt(settings: Settings, *, enabled: bool) -> GdeltProvider:
    """Crea el adaptador de GDELT con su pausa y su espera tras un 429.

    Args:
        settings: Configuración de la aplicación.
        enabled: Si puede consultar. Las búsquedas usan ``GDELT_ENABLED``; el
            diagnóstico diario aprobado por Benji lo activa solo para su D1.

    Returns:
        El adaptador.
    """
    return GdeltProvider(
        ProviderHttpClient(
            Provider.GDELT,
            timeout_seconds=settings.provider_timeout_seconds,
            max_attempts=settings.provider_max_attempts,
            max_concurrency=settings.provider_max_concurrency,
            min_interval_seconds=settings.gdelt_min_interval_seconds,
            rate_limit_wait_seconds=settings.gdelt_rate_limit_wait_seconds,
        ),
        enabled=enabled,
    )


def build_provider(
    provider: Provider, settings: Settings, engine: AsyncEngine | None = None
) -> NewsProviderPort:
    """Crea el adaptador de un proveedor.

    Args:
        provider: Proveedor.
        settings: Configuración de la aplicación.
        engine: Conexión a la base; la necesita el índice local.

    Returns:
        El adaptador listo para consultar. SearchApi sin llave devuelve un
        adaptador que responde ``is_configured() == False``.

    Raises:
        ValueError: Si se pide el índice local sin ``engine``.
    """
    if provider is Provider.LOCAL_INDEX:
        if engine is None:
            raise ValueError("El índice local necesita la conexión a la base (engine).")
        return LocalIndexProvider(engine)
    if provider is Provider.GDELT:
        return build_gdelt(settings, enabled=settings.gdelt_enabled)
    if provider is Provider.GOOGLE_NEWS_RSS:
        if settings.news_rss_enabled:
            # Que quede en el registro cada vez: no debe pasar en producción.
            logger.warning(
                "Google News RSS habilitado (NEWS_RSS_ENABLED=true): solo para desarrollo; "
                "sus términos solo permiten uso personal y no comercial (ADR-0011)."
            )
        return GoogleNewsRssProvider(
            ProviderHttpClient(
                provider,
                timeout_seconds=settings.provider_timeout_seconds,
                max_attempts=settings.provider_max_attempts,
                max_concurrency=settings.provider_max_concurrency,
            ),
            enabled=settings.news_rss_enabled,
        )
    key = settings.searchapi_api_key
    if key is None or not key.get_secret_value():
        # Sin llave: el adaptador existe pero dice que no está configurado y
        # la consulta se salta con aviso.
        return SearchApiProvider(None)
    return SearchApiProvider(
        ProviderHttpClient(
            provider,
            timeout_seconds=settings.searchapi_timeout_seconds,
            max_attempts=settings.provider_max_attempts,
            max_concurrency=settings.provider_max_concurrency,
            # La llave viaja en el encabezado, nunca en la URL: así no
            # aparece en los registros de httpx2 ni en provider_queries.
            headers={"Authorization": f"Bearer {key.get_secret_value()}"},
        )
    )
