"""Arma los adaptadores de proveedores a partir de la configuración.

Lo usan el comando de prueba y, en F4, el worker. Así la configuración de
tiempos, reintentos y llaves vive en un solo lugar.

No hace: no decide qué proveedores usar en una búsqueda.
"""

from app.adapters.providers.gdelt import GdeltProvider
from app.adapters.providers.google_news_rss import GoogleNewsRssProvider
from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.providers import NewsProviderPort
from app.core.config import Settings
from app.domain.queries import Provider


def build_provider(provider: Provider, settings: Settings) -> NewsProviderPort:
    """Crea el adaptador de un proveedor.

    Args:
        provider: Proveedor.
        settings: Configuración de la aplicación.

    Returns:
        El adaptador listo para consultar.

    Raises:
        ValueError: Si el proveedor todavía no tiene adaptador.
    """
    if provider is Provider.GDELT:
        return GdeltProvider(
            ProviderHttpClient(
                provider,
                timeout_seconds=settings.provider_timeout_seconds,
                max_attempts=settings.provider_max_attempts,
                max_concurrency=settings.provider_max_concurrency,
                min_interval_seconds=settings.gdelt_min_interval_seconds,
                rate_limit_wait_seconds=settings.gdelt_rate_limit_wait_seconds,
            )
        )
    if provider is Provider.GOOGLE_NEWS_RSS:
        return GoogleNewsRssProvider(
            ProviderHttpClient(
                provider,
                timeout_seconds=settings.provider_timeout_seconds,
                max_attempts=settings.provider_max_attempts,
                max_concurrency=settings.provider_max_concurrency,
            )
        )
    raise ValueError(f"Proveedor sin adaptador todavía: {provider.value}")
