"""Leer el cuerpo de una nota con trafilatura (§9, paso 4; ADR-0015).

Baja la página con el cliente HTTP compartido (tiempo máximo, reintentos,
User-Agent propio; ADR-0010) y le pide a trafilatura solo el cuerpo: sin
menús, anuncios, comentarios ni tablas. trafilatura es lento para la CPU
(analiza todo el HTML), así que corre en un hilo aparte para no frenar a las
demás descargas.

Firma confirmada con trafilatura 2.3.1: ``extract(filecontent, url=...,
favor_precision=..., include_comments=..., include_tables=...)`` devuelve el
texto o ``None``.

No hace: no decide si el texto alcanza (``app.domain.extraction``) ni lo
guarda.
"""

import asyncio

import trafilatura

from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.extraction import Extraction
from app.core.config import Settings
from app.domain.errors import ProviderError

# Nombre en los mensajes y el registro del cliente HTTP.
PAGES = "paginas"


class TrafilaturaExtractor:
    """``TextExtractorPort`` con trafilatura."""

    def __init__(self, http: ProviderHttpClient) -> None:
        """Recibe el cliente HTTP.

        Args:
            http: Cliente HTTP configurado para páginas de medios.
        """
        self._http = http

    async def aclose(self) -> None:
        """Cierra las conexiones HTTP."""
        await self._http.aclose()

    async def extract(self, url: str) -> Extraction:
        """Ver ``TextExtractorPort.extract``."""
        try:
            response = await self._http.get(url, {})
        except ProviderError as error:
            return Extraction(None, error.message)
        # Precisión antes que cantidad: mejor un cuerpo corto y limpio que
        # uno con pies de foto y notas relacionadas mezcladas.
        text = await asyncio.to_thread(
            trafilatura.extract,
            response.text,
            url=url,
            favor_precision=True,
            include_comments=False,
            include_tables=False,
        )
        if not text:
            return Extraction(None, "trafilatura no encontró el cuerpo de la nota.")
        return Extraction(text)


def build_extractor(settings: Settings) -> TrafilaturaExtractor:
    """Crea el extractor con el tiempo máximo y la concurrencia de la configuración.

    Args:
        settings: Configuración (``EXTRACTION_TIMEOUT_SECONDS``,
            ``EXTRACTION_CONCURRENCY``).

    Returns:
        El extractor listo.
    """
    return TrafilaturaExtractor(
        ProviderHttpClient(
            PAGES,
            timeout_seconds=settings.extraction_timeout_seconds,
            max_attempts=settings.provider_max_attempts,
            max_concurrency=settings.extraction_concurrency,
        )
    )
