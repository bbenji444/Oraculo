"""Tareas periódicas de Celery: ingesta al índice local y limpieza (ADR-0013).

``celery beat`` (el reloj que arranca ``make up``) las encola según
``beat_schedule`` en ``celery_app.py``; el worker las ejecuta. Cada tarea es
una envoltura delgada: la lógica vive en ``app.worker.ingest_jobs`` y en los
casos de uso, y cada corrida queda en ``ingest_runs``.

No hace: no busca noticias para un usuario (eso llega en F4).
"""

import asyncio
import logging

from app.application.use_cases.ingest import IngestReport
from app.core.config import get_settings
from app.worker.celery_app import celery_app
from app.worker.ingest_jobs import run_ingest, run_purge

logger = logging.getLogger(__name__)

INGEST_TASK = "ingest.news"
PURGE_TASK = "ingest.purge"


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
    """Aplica las retenciones: notas completas y frases del cuerpo.

    Returns:
        Cuántas notas se borraron y a cuántas se les quitó el cuerpo.
    """
    report = asyncio.run(run_purge(get_settings()))
    result = {"deleted": report.notes_deleted, "bodies_cleared": report.bodies_cleared}
    logger.info("Limpieza del índice local", extra=result)
    return result
