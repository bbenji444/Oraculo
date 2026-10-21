"""Arma y corre la lectura de una nota de un caso con piezas reales (Fase 9.4, ADR-0103).

Es el punto donde se juntan la base y la IA elegida (``LLM_PROVIDER``) para
proponer las entidades de una nota. Lo usan la tarea de Celery
(``app.worker.tasks.extract_case_entities``) y el comando
``make extraer-entidades``, para que los dos hagan exactamente lo mismo.

No hace: no decide qué notas se leen ni muestra nada.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.llm.factory import (
    EntityExtractorSetup,
    MissingLLMKeyError,
    build_entity_extractor,
)
from app.adapters.persistence.entities_repository import PostgresEntityRepository
from app.application.audit import Actor
from app.application.use_cases.entities import ExtractCaseArticle, ExtractionOutcome
from app.application.use_cases.reports import LLMPrices
from app.core.config import Settings
from app.domain.entity_extraction import CaseArticleEntitiesStatus

logger = logging.getLogger(__name__)


def prices_of(setup: EntityExtractorSetup) -> LLMPrices:
    """Precios de la IA elegida, para guardar el costo de cada lectura.

    Args:
        setup: La IA con sus precios.

    Returns:
        Los precios.
    """
    return LLMPrices(setup.provider, setup.price_input_per_million, setup.price_output_per_million)


@asynccontextmanager
async def extraction_pipeline(
    settings: Settings,
) -> AsyncIterator[tuple[ExtractCaseArticle, EntityExtractorSetup, PostgresEntityRepository]]:
    """Abre la base y la IA, arma ``ExtractCaseArticle`` y las cierra al salir.

    Args:
        settings: Configuración.

    Yields:
        El caso de uso, la IA (con sus precios) y el repositorio.

    Raises:
        MissingLLMKeyError: Si falta la llave de la IA elegida.
    """
    setup = build_entity_extractor(settings)
    engine = create_async_engine(settings.database_url(), pool_pre_ping=True)
    repository = PostgresEntityRepository(engine)
    try:
        yield ExtractCaseArticle(repository, setup.extractor, prices_of(setup)), setup, repository
    finally:
        await setup.extractor.aclose()
        await engine.dispose()


async def run_entity_extraction(
    settings: Settings, case_id: UUID, article_id: int, requested_by: str
) -> ExtractionOutcome | None:
    """Lee una nota del caso. Sin llave de la IA, la deja ``failed`` para reintentar.

    Args:
        settings: Configuración.
        case_id: Caso.
        article_id: Nota.
        requested_by: Quién la pidió (va en la bitácora).

    Returns:
        Qué pasó con la nota, o ``None`` si no había nada que hacer.
    """
    try:
        async with extraction_pipeline(settings) as (use_case, _setup, _repository):
            return await use_case.execute(case_id, article_id, Actor(requested_by))
    except MissingLLMKeyError as error:
        logger.warning(
            "No se pueden leer las entidades: %s",
            error,
            extra={"case_id": str(case_id), "article_id": article_id},
        )
        engine = create_async_engine(settings.database_url())
        try:
            # Sin llave no se gasta nada: queda "failed" para que el caso
            # ofrezca "Analizar pendientes" cuando ya esté configurada.
            await PostgresEntityRepository(engine).set_status(
                case_id, [article_id], CaseArticleEntitiesStatus.FAILED
            )
        finally:
            await engine.dispose()
        return None
