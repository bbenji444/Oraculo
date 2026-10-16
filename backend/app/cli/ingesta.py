"""Comando ``make ingesta``: corre la ingesta una vez, ahora (ADR-0013).

Hace lo mismo que la tarea que ``celery beat`` dispara cada 15 minutos y
muestra, por fuente, cuántas notas leyó y guardó, más 5 ejemplos reales
(CLAUDE.md §2.6). Sirve para verificar la ingesta sin esperar al reloj.

GDELT es gratis y sin límite en su servidor de archivos (~8 MB por corrida).
Los RSS de medios solo se leen si ``MEDIA_RSS_ENABLED=true`` y el medio está
activo en ``fuentes/medios_rss.csv``.

Uso: ``make ingesta``

No hace: no descarga historial (eso es ``make ingesta-historial``).
"""

import asyncio
import logging
from collections.abc import Sequence

from app.application.clock import MEXICO_CITY
from app.application.use_cases.ingest import IngestReport
from app.core.config import get_settings
from app.geodata.consola import configure_cli_logging, heading
from app.worker.ingest_jobs import run_ingest

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024


def show_report(report: IngestReport) -> None:
    """Muestra una corrida: números y ejemplos.

    Args:
        report: Reporte del caso de uso.
    """
    heading(logger, f"{report.source} · {report.item}")
    if report.status == "error":
        logger.error(f"Falló: {report.message}")
        return
    if report.status == "skipped":
        logger.info(f"Sin novedades: {report.message}")
        return
    logger.info(
        f"{report.bytes_downloaded / _BYTES_PER_MB:.1f} MB · {report.items_seen} leídas · "
        f"{report.items_kept} válidas · {report.items_new} nuevas en el índice"
    )
    for number, item in enumerate(report.sample, start=1):
        local = item.published_at.astimezone(MEXICO_CITY).strftime("%d/%m/%Y %H:%M")
        states = ",".join(item.gdelt_states) or "—"
        logger.info(f"{number}. {item.title}")
        logger.info(f"   {item.source_domain} · {local} · estados GDELT: {states}")
        logger.info(f"   {item.url}")


async def run() -> int:
    """Corre la ingesta y muestra el resultado.

    Returns:
        0 si ninguna fuente falló; 1 si alguna falló.
    """
    settings = get_settings()
    summary = await run_ingest(settings)
    reports: Sequence[IngestReport] = [
        *([summary.gdelt] if summary.gdelt else []),
        *summary.media,
    ]
    if not settings.gdelt_gkg_enabled:
        logger.warning("GDELT apagado (GDELT_GKG_ENABLED=false).")
    if not settings.media_rss_enabled:
        logger.warning("RSS de medios apagados (MEDIA_RSS_ENABLED=false).")
    for report in reports:
        show_report(report)
    return 1 if any(report.status == "error" for report in reports) else 0


def main() -> None:
    """Punto de entrada de ``python -m app.cli.ingesta``."""
    configure_cli_logging()
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
