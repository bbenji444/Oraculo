"""Tareas de Celery: ingesta al índice local, limpieza (ADR-0013) y búsquedas (§9).

``celery beat`` (el reloj que arranca ``make up``) las encola según
``beat_schedule`` en ``celery_app.py``; el worker las ejecuta. Cada tarea es
una envoltura delgada: la lógica vive en ``app.worker.ingest_jobs``,
``app.worker.search_jobs`` y los casos de uso. La búsqueda no la programa el
reloj: la encola quien la pide (el comando ``make buscar`` y, en F5, la API).

No hace: no contiene lógica de negocio.
"""

import asyncio
import logging
from uuid import UUID

from app.application.use_cases.ingest import IngestReport
from app.core.config import get_settings
from app.worker.celery_app import celery_app
from app.worker.ingest_jobs import run_ingest, run_purge
from app.worker.search_jobs import purge_article_texts, run_search_job

logger = logging.getLogger(__name__)

INGEST_TASK = "ingest.news"
PURGE_TASK = "ingest.purge"
SEARCH_TASK = "search.run"


def _log_report(report: IngestReport) -> None:
    fields = {
        "source": report.source,
        "item": report.item,
        "status": report.status,
        "items_new": report.items_new,
        "items_kept": report.items_kept,
        "bytes_downloaded": report.bytes_downloaded,
    }
    if report.status == "error":
        logger.warning("Ingesta con error: %s", report.message, extra=fields)
    else:
        logger.info("Ingesta terminada", extra=fields)


@celery_app.task(name=INGEST_TASK)
def ingest_news() -> dict[str, int]:
    """Corre una vez la ingesta de las fuentes encendidas.

    Returns:
        Notas nuevas por fuente (``{"gdelt_ngrams": 300, "rss:la-jornada": 4}``),
        sumando los minutos de ngramas, para verlas en el resultado de la tarea.
    """
    summary = asyncio.run(run_ingest(get_settings()))
    new_by_source: dict[str, int] = {}
    for report in summary.reports:
        _log_report(report)
        new_by_source[report.source] = new_by_source.get(report.source, 0) + report.items_new
    return new_by_source


@celery_app.task(name=PURGE_TASK)
def purge_news_index() -> dict[str, int]:
    """Aplica las retenciones: notas del índice, frases del cuerpo y textos extraídos.

    Returns:
        Cuántas notas se borraron, a cuántas se les quitó el cuerpo y cuántos
        textos de búsquedas se borraron (ADR-0015).
    """
    settings = get_settings()
    report = asyncio.run(run_purge(settings))
    texts = asyncio.run(purge_article_texts(settings))
    result = {
        "deleted": report.notes_deleted,
        "bodies_cleared": report.bodies_cleared,
        "texts_deleted": texts,
    }
    logger.info("Limpieza del índice local", extra=result)
    return result


@celery_app.task(name=SEARCH_TASK)
def run_search(search_id: str) -> dict[str, object]:
    """Corre una búsqueda guardada en ``pending`` (las 8 etapas de §9).

    Args:
        search_id: Id de la búsqueda (texto: los mensajes de Celery son JSON).

    Returns:
        Estado final, notas, créditos y costo, para verlos en el resultado.
    """
    report = asyncio.run(run_search_job(get_settings(), UUID(search_id)))
    result: dict[str, object] = {
        "status": report.status.value,
        "articles": report.articles,
        "credits_used": report.credits_used,
        "llm_cost_usd": round(report.llm_cost_usd, 4),
    }
    logger.info("Búsqueda terminada", extra={"search_id": search_id, **result})
    return result
