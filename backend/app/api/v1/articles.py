"""Endpoint ``/api/v1/articles/{id}`` (especificación §13).

El detalle de una nota: metadatos, resumen de la IA, juicios por concepto,
todas sus menciones de lugar y quién la encontró. Nunca el texto completo
(CLAUDE.md §8).

No hace: no valida reglas de negocio.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.api.errors import ERROR_RESPONSES
from app.api.v1.schemas.articles import ArticleDetailOut
from app.application.ports.search_reads import ArticleReaderPort
from app.application.use_cases.search_reads import GetArticle

router = APIRouter(prefix="/articles", tags=["notas"], responses=ERROR_RESPONSES)


def get_article_reader(request: Request) -> ArticleReaderPort:
    """Lecturas de notas creadas al arrancar.

    Args:
        request: Petición actual.

    Returns:
        El lector compartido.
    """
    reader: ArticleReaderPort = request.app.state.article_store
    return reader


Articles = Annotated[ArticleReaderPort, Depends(get_article_reader)]


@router.get("/{article_id}", response_model=ArticleDetailOut, summary="Detalle de una nota")
async def get_article(
    articles: Articles, article_id: Annotated[int, Path(description="Id de la nota.")]
) -> ArticleDetailOut:
    """Metadatos, resumen, conceptos, lugares y proveedores de una nota."""
    return ArticleDetailOut.from_detail(await GetArticle(articles).execute(article_id))
