"""Extraer el texto de las notas de una búsqueda (§9, paso 4; ADR-0015).

Lee varias notas a la vez, con un tope (``EXTRACTION_CONCURRENCY``) para no
saturar a los medios ni a la conexión. Cada nota termina con su texto: el
cuerpo, o título + fragmento si no se pudo.

Las publicaciones de redes sociales (Facebook, X, YouTube...) no se
descargan (ADR-0115): piden iniciar sesión y la descarga solo gastaba el
tiempo máximo. Se procesan con título + fragmento desde el principio. Lo
mismo los links ``google.com/goto`` que Google web no resolvió: descargarlos
daría la página «Verificando tu solicitud» de Google, no la nota.

No hace: no guarda nada ni llama a la IA.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from app.application.ports.extraction import TextExtractorPort
from app.domain.dedupe import DedupedArticle
from app.domain.extraction import ProcessingText, processing_text
from app.domain.platforms import is_google_redirect, is_social

# Por qué una red social se procesa con título + fragmento (queda en el texto
# de respaldo; el analista lo ve como «solo título y fragmento»).
SOCIAL_FALLBACK_REASON = (
    "Publicación de red social: no se descarga (pide iniciar sesión); se usa título y fragmento."
)
# Por qué un link de Google web sin resolver se procesa con título + fragmento.
GOOGLE_LINK_FALLBACK_REASON = (
    "Link de Google sin resolver: no se descarga (Google pide verificar); "
    "se usa título y fragmento."
)


@dataclass(frozen=True, slots=True)
class ArticleText:
    """Una nota con el texto que se procesará.

    Attributes:
        article: La nota (ya sin duplicados).
        text: Su texto y cómo se obtuvo.
    """

    article: DedupedArticle
    text: ProcessingText


class ExtractTexts:
    """Lee el cuerpo de muchas notas con concurrencia limitada."""

    def __init__(self, extractor: TextExtractorPort, concurrency: int) -> None:
        """Recibe el extractor y el tope de lecturas simultáneas.

        Args:
            extractor: Lector de páginas.
            concurrency: Lecturas simultáneas (``EXTRACTION_CONCURRENCY``).
        """
        self._extractor = extractor
        self._semaphore = asyncio.Semaphore(concurrency)

    async def _one(self, item: DedupedArticle) -> ArticleText:
        article = item.article
        if is_social(article.source_domain, article.url, article.source_name):
            text = processing_text(article.title, article.snippet, None, SOCIAL_FALLBACK_REASON)
            return ArticleText(item, text)
        if is_google_redirect(article.url):
            text = processing_text(
                article.title, article.snippet, None, GOOGLE_LINK_FALLBACK_REASON
            )
            return ArticleText(item, text)
        async with self._semaphore:
            # La URL original del proveedor: la canónica es para comparar y
            # algunos medios no responden igual sin sus parámetros.
            extraction = await self._extractor.extract(article.url)
        text = processing_text(article.title, article.snippet, extraction.text, extraction.failure)
        return ArticleText(item, text)

    async def run(self, articles: Sequence[DedupedArticle]) -> list[ArticleText]:
        """Extrae el texto de todas las notas, en el orden recibido.

        Args:
            articles: Notas sin duplicados.

        Returns:
            Una entrada por nota.
        """
        return list(await asyncio.gather(*(self._one(a) for a in articles)))
