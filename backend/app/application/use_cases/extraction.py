"""Extraer el texto de las notas de una búsqueda (§9, paso 4; ADR-0015).

Lee varias notas a la vez, con un tope (``EXTRACTION_CONCURRENCY``) para no
saturar a los medios ni a la conexión. Cada nota termina con su texto: el
cuerpo, o título + fragmento si no se pudo.

No hace: no guarda nada ni llama a la IA.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from app.application.ports.extraction import TextExtractorPort
from app.domain.dedupe import DedupedArticle
from app.domain.extraction import ProcessingText, processing_text


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
        async with self._semaphore:
            # La URL original del proveedor: la canónica es para comparar y
            # algunos medios no responden igual sin sus parámetros.
            extraction = await self._extractor.extract(item.article.url)
        article = item.article
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
