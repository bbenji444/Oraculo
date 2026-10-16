"""Arma las fuentes de la ingesta a partir de la configuración (ADR-0013).

Lo usan el comando ``make ingesta`` y las tareas de Celery.

No hace: no decide cuándo correr (eso es ``celery beat``).
"""

from app.adapters.ingest.gdelt_gkg import GdeltGkgSource
from app.adapters.ingest.gdelt_ngrams import GdeltNgramsSource
from app.adapters.ingest.media_rss import MediaRssSource
from app.adapters.providers.http import ProviderHttpClient
from app.core.config import Settings
from app.domain.news_index import MexicoMentions
from app.domain.queries import Provider
from app.geodata.fips import read_fips_to_inegi

# Un GKG pesa ~8 MB: con 60 s sobra aun en una conexión lenta.
GKG_DOWNLOAD_TIMEOUT_SECONDS = 60.0


def build_gkg_source(settings: Settings) -> GdeltGkgSource:
    """Fuente de archivos GKG de GDELT (servidor de archivos, sin el límite de la API).

    Args:
        settings: Configuración.

    Returns:
        La fuente lista.
    """
    http = ProviderHttpClient(
        Provider.GDELT,
        timeout_seconds=max(settings.provider_timeout_seconds, GKG_DOWNLOAD_TIMEOUT_SECONDS),
        max_attempts=settings.provider_max_attempts,
        max_concurrency=1,
        rate_limit_wait_seconds=settings.gdelt_rate_limit_wait_seconds,
    )
    return GdeltGkgSource(http, read_fips_to_inegi())


def build_rss_source(settings: Settings) -> MediaRssSource:
    """Lector de RSS de medios.

    Args:
        settings: Configuración.

    Returns:
        La fuente lista.
    """
    http = ProviderHttpClient(
        Provider.GOOGLE_NEWS_RSS,
        timeout_seconds=settings.provider_timeout_seconds,
        max_attempts=settings.provider_max_attempts,
        max_concurrency=settings.provider_max_concurrency,
    )
    return MediaRssSource(http)


def build_ngrams_source(settings: Settings, state_terms: list[str]) -> GdeltNgramsSource:
    """Fuente de ngramas de GDELT (texto completo por minuto, ADR-0014).

    Args:
        settings: Configuración.
        state_terms: Nombres y términos de los estados (``state_terms`` del
            repositorio de regiones), para reconocer notas de México.

    Returns:
        La fuente lista.
    """
    http = ProviderHttpClient(
        Provider.GDELT,
        # Un minuto de ngramas llegó a pesar 12 MB: mismo margen que el GKG.
        timeout_seconds=max(settings.provider_timeout_seconds, GKG_DOWNLOAD_TIMEOUT_SECONDS),
        max_attempts=settings.provider_max_attempts,
        max_concurrency=1,
        rate_limit_wait_seconds=settings.gdelt_rate_limit_wait_seconds,
    )
    return GdeltNgramsSource(http, MexicoMentions(state_terms))
