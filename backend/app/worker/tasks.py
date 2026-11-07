"""Tareas de Celery: ingesta, limpieza, búsquedas, entidades y corridas automáticas.

Ingesta y limpieza (ADR-0013), búsquedas (§9), entidades (9.4) y las corridas
automáticas del monitor FGR (F12.8, ADR-0031).

``celery beat`` (el reloj que arranca ``make up``) las encola según
``beat_schedule`` en ``celery_app.py``; el worker las ejecuta. Cada tarea es
una envoltura delgada: la lógica vive en ``app.worker.ingest_jobs``,
``app.worker.search_jobs``, ``app.worker.entity_jobs`` y los casos de uso. La
búsqueda y la lectura de entidades no las programa el reloj: las encola quien
las pide (la API y los comandos).

No hace: no contiene lógica de negocio.
"""

import asyncio
import logging
from uuid import UUID

from app.adapters.queue.celery_queue import ENTITIES_TASK, SEARCH_TASK
from app.application.use_cases.ingest import IngestReport
from app.core.config import get_settings
from app.worker.automatic_jobs import run_automatic_job
from app.worker.celery_app import AUTOMATIC_RUN_TASK, DELIVERIES_TASK, celery_app
from app.worker.delivery_jobs import send_due_deliveries
from app.worker.entity_jobs import run_entity_extraction
from app.worker.ingest_jobs import run_ingest, run_purge
from app.worker.search_jobs import purge_article_texts, run_search_job

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


@celery_app.task(name=ENTITIES_TASK)
def extract_case_entities(case_id: str, article_id: int, requested_by: str) -> dict[str, object]:
    """Lee con la IA una nota de un caso y deja sus entidades como sugerencias (9.4).

    Args:
        case_id: Id del caso (texto: los mensajes de Celery son JSON).
        article_id: Nota.
        requested_by: Quién la pidió (va en la bitácora).

    Returns:
        Estado de la nota, cuántas sugerencias y el costo, para verlos en el
        resultado.
    """
    outcome = asyncio.run(
        run_entity_extraction(get_settings(), UUID(case_id), article_id, requested_by)
    )
    result: dict[str, object] = {"status": outcome.status.value if outcome else "nothing_to_do"}
    if outcome is not None:
        result |= {
            "reused": outcome.reused,
            "proposals": len(outcome.extraction.reviewed.proposals) if outcome.extraction else 0,
            "cost_usd": round(outcome.cost_usd, 6),
        }
    logger.info(
        "Entidades de una nota del caso",
        extra={"case_id": case_id, "article_id": article_id, **result},
    )
    return result


@celery_app.task(name=AUTOMATIC_RUN_TASK)
def automatic_run() -> dict[str, object]:
    """Corrida automática del monitor FGR (la lanza el reloj a las 07:00, 15:00 y 23:00).

    Returns:
        La búsqueda creada, su estado, notas, costo y la ruta del PDF.
    """
    summary = asyncio.run(run_automatic_job(get_settings()))
    result: dict[str, object] = {
        "search_id": str(summary.search_id),
        "corrida": summary.scheduled_for.isoformat(),
        "status": summary.report.status.value,
        "articles": summary.report.articles,
        "credits_used": summary.report.credits_used,
        "llm_cost_usd": round(summary.report.llm_cost_usd, 4),
        "pdf": str(summary.pdf_path) if summary.pdf_path else None,
    }
    logger.info("Corrida automática terminada", extra=result)
    return result


@celery_app.task(name=DELIVERIES_TASK)
def send_deliveries() -> dict[str, int]:
    """Manda los envíos pendientes, reintentos incluidos (ADR-0039).

    Returns:
        Cuántos se intentaron, mandaron y fallaron.
    """
    report = asyncio.run(send_due_deliveries(get_settings()))
    result = {"attempted": report.attempted, "sent": report.sent, "failed": report.failed}
    if report.attempted:
        logger.info("Envíos pendientes", extra=result)
    return result
