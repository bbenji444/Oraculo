"""Arma los adaptadores de proveedores a partir de la configuración.

Lo usan el comando de prueba y, en F4, el worker. Así la configuración de
tiempos, reintentos y llaves vive en un solo lugar.

No hace: no decide qué proveedores usar en una búsqueda.
"""

import httpx2
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.providers.browserwork import ENGINES, BrowserWorkProvider
from app.adapters.providers.gdelt import GdeltProvider
from app.adapters.providers.google_news_rss import GoogleNewsRssProvider
from app.adapters.providers.http import ProviderHttpClient
from app.adapters.providers.local_index import LocalIndexProvider
from app.adapters.providers.searchapi import SearchApiProvider
from app.adapters.providers.searchapi_web import (
    GOTO_MAX_ATTEMPTS,
    GOTO_MAX_CONCURRENCY,
    GOTO_TIMEOUT_SECONDS,
    NO_CREDIT_STATUSES,
    SearchApiWebProvider,
)
from app.application.ports.providers import NewsProviderPort
from app.core.config import Settings
from app.domain.queries import Provider


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
    if provider in ENGINES:
        return BrowserWorkProvider(
            provider,
            ProviderHttpClient(
                provider,
                timeout_seconds=settings.provider_timeout_seconds,
                max_attempts=settings.provider_max_attempts,
                # Un trabajo a la vez en su servidor: no tiene caso mandar más.
                max_concurrency=1,
            ),
            base_url=settings.browserwork_base_url or None,
            pages=settings.browserwork_pages,
            timeout_seconds=settings.browserwork_timeout_seconds,
            poll_seconds=settings.browserwork_poll_seconds,
        )
    if provider is Provider.GOOGLE_NEWS_RSS:
        return GoogleNewsRssProvider(
            ProviderHttpClient(
                provider,
                timeout_seconds=settings.provider_timeout_seconds,
                max_attempts=settings.provider_max_attempts,
                max_concurrency=settings.provider_max_concurrency,
            ),
            enabled=settings.news_rss_enabled,
        )
    if provider is Provider.SEARCHAPI_WEB:
        return build_searchapi_web(settings)
    # Sin llave el cliente es None: el adaptador existe pero dice que no está
    # configurado y la consulta se salta con aviso.
    return SearchApiProvider(_searchapi_http(provider, settings), settings.searchapi_max_pages)


def _searchapi_http(
    provider: Provider,
    settings: Settings,
    *,
    no_credit_statuses: frozenset[int] = frozenset(),
    transport: httpx2.AsyncBaseTransport | None = None,
) -> ProviderHttpClient | None:
    """Cliente de SearchApi con la llave en el encabezado, o ``None`` sin llave.

    Args:
        provider: Motor de SearchApi (Google News o Google web).
        settings: Configuración de la aplicación.
        no_credit_statuses: Códigos de «sin créditos» que no se reintentan.
        transport: Transporte de ``httpx2``; solo para las pruebas.

    Returns:
        El cliente, o ``None`` si falta ``SEARCHAPI_API_KEY``.
    """
    key = settings.searchapi_api_key
    if key is None or not key.get_secret_value():
        return None
    return ProviderHttpClient(
        provider,
        timeout_seconds=settings.searchapi_timeout_seconds,
        max_attempts=settings.provider_max_attempts,
        max_concurrency=settings.provider_max_concurrency,
        # La llave viaja en el encabezado, nunca en la URL: así no
        # aparece en los registros de httpx2 ni en provider_queries.
        headers={"Authorization": f"Bearer {key.get_secret_value()}"},
        transport=transport,
        no_credit_statuses=no_credit_statuses,
    )


def build_searchapi_web(
    settings: Settings, transport: httpx2.AsyncBaseTransport | None = None
) -> SearchApiWebProvider:
    """Crea el adaptador de Google web (SearchApi, motor ``google``, ADR-0115).

    Lleva dos clientes: el de SearchApi, con la llave, y uno aparte para leer
    a dónde llevan los links ``google.com/goto``. Ese segundo cliente **no
    lleva la llave** (se le pide a Google, no a SearchApi), no sigue
    redirecciones, espera poco y no reintenta.

    El de SearchApi no reintenta los códigos de «sin créditos»
    (``NO_CREDIT_STATUSES``): sin saldo, reintentar con espera solo retrasa
    la búsqueda. El motor de Google News se deja como estaba (su 429 se
    reintenta) para no cambiar las corridas automáticas.

    Args:
        settings: Configuración de la aplicación.
        transport: Transporte de ``httpx2`` para los dos clientes; solo las
            pruebas lo pasan (``MockTransport``).

    Returns:
        El adaptador; sin ``SEARCHAPI_API_KEY`` dice que no está configurado.
    """
    resolver = ProviderHttpClient(
        "google_goto",
        timeout_seconds=GOTO_TIMEOUT_SECONDS,
        max_attempts=GOTO_MAX_ATTEMPTS,
        max_concurrency=GOTO_MAX_CONCURRENCY,
        follow_redirects=False,
        transport=transport,
    )
    return SearchApiWebProvider(
        _searchapi_http(
            Provider.SEARCHAPI_WEB,
            settings,
            no_credit_statuses=NO_CREDIT_STATUSES,
            transport=transport,
        ),
        resolver,
        settings.searchapi_web_max_pages,
    )
