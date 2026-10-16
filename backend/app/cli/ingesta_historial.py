"""Comando ``make ingesta-historial``: notas de días anteriores de GDELT (ADR-0013).

La ingesta periódica solo junta notas desde que ``make up`` está corriendo.
Este comando baja los archivos GKG de días anteriores, en dos pasos
(CLAUDE.md §2.6):

1. **Vista previa** (``make ingesta-historial DIAS=7``): mide cada archivo
   pendiente **sin bajarlo** (solo encabezados) y muestra cuántos son y cuánto
   pesan. Para mostrar 5 ejemplos reales baja **un** archivo de muestra (el
   más reciente pendiente, ~7 MB) y lo guarda en el índice.
2. **Descarga** (``make ingesta-historial DIAS=7 DESCARGAR=si``): baja el
   resto. Solo después de que Benji vio la vista previa y dio su OK.

Cada archivo pasa por el mismo camino que la ingesta periódica (MD5,
filtro de español y México, deduplicación por URL, registro en
``ingest_runs``); un archivo ya procesado nunca se vuelve a bajar.

No hace: no lee RSS de medios (no tienen historial).
"""

import argparse
import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.ingest.factory import build_gkg_source
from app.adapters.ingest.gdelt_gkg import history_urls
from app.adapters.persistence.news_index_repository import (
    PostgresIngestRunLog,
    PostgresNewsIndex,
)
from app.application.use_cases.ingest import HistoryPlan, IngestGdeltGkg, PlanGdeltHistory
from app.cli.ingesta import show_report
from app.core.config import Settings, get_settings
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024
_SECONDS_PER_MINUTE = 60
# Medido el 16/10/2026 con el reloj de Celery: 8.7 s y 11.8 s por archivo
# (descarga + lectura + guardado). Sirve para estimar, no es un límite.
MEASURED_SECONDS_PER_FILE = 10
# Cada cuántos archivos revisados se avisa del avance (un día = 96).
PROGRESS_EVERY = 96
# Motivos de archivos que no se pudieron medir que se muestran.
MAX_FAILED_SHOWN = 5


def _show_plan(plan: HistoryPlan, total: int) -> None:
    logger.info(
        f"{total} cuartos de hora · {plan.already_done} ya en el índice · "
        f"{plan.missing} sin archivo en GDELT · {len(plan.failed)} no se pudieron medir"
    )
    minutes = len(plan.files) * MEASURED_SECONDS_PER_FILE / _SECONDS_PER_MINUTE
    logger.info(
        f"Pendientes: {len(plan.files)} archivos · {plan.total_bytes / _BYTES_PER_MB:,.0f} MB "
        f"de descarga · ≈ {minutes:,.0f} min"
    )
    for reason in plan.failed[:MAX_FAILED_SHOWN]:
        logger.warning(reason)


def _progress(done: int, total: int) -> None:
    if done % PROGRESS_EVERY == 0 or done == total:
        logger.info(f"Revisados {done} de {total} archivos")


async def run(days: int, download: bool, settings: Settings) -> int:
    """Vista previa y, si se pidió, descarga del historial.

    Args:
        days: Días hacia atrás.
        download: Si se baja todo lo pendiente.
        settings: Configuración.

    Returns:
        0 si todo salió bien; 1 si algún archivo falló.
    """
    engine = create_async_engine(settings.database_url())
    source = build_gkg_source(settings)
    runs = PostgresIngestRunLog(engine)
    ingest = IngestGdeltGkg(source, PostgresNewsIndex(engine), runs)
    try:
        urls = history_urls(datetime.now(UTC), days)
        heading(logger, f"Historial de GDELT · últimos {days} días (solo se miden, sin bajar)")
        plan = await PlanGdeltHistory(source, runs).plan(urls, _progress)
        _show_plan(plan, len(urls))
        if not plan.files:
            logger.info("Nada que bajar.")
            return 0
        sample, *rest = plan.files
        logger.info(
            f"Se baja 1 archivo de muestra ({sample.size / _BYTES_PER_MB:.1f} MB) "
            "para mostrar ejemplos reales; queda guardado en el índice."
        )
        reports = [await ingest.run_file(sample)]
        show_report(reports[0])
        if not download:
            rest_mb = sum(file.size for file in rest) / _BYTES_PER_MB
            logger.warning(f"No se bajó nada más. Faltan {len(rest)} archivos ({rest_mb:,.0f} MB).")
            logger.info(f"Para bajarlos: wsl make ingesta-historial DIAS={days} DESCARGAR=si")
            return 0
        heading(logger, f"Descargando {len(rest)} archivos")
        for number, file in enumerate(rest, start=1):
            report = await ingest.run_file(file)
            reports.append(report)
            line = f"{number}/{len(rest)} {file.name}: {report.status}, {report.items_new} nuevas"
            if report.status == "error":
                logger.warning(f"{line} — {report.message}")
            else:
                logger.info(line)
        new = sum(report.items_new for report in reports)
        errors = sum(report.status == "error" for report in reports)
        heading(logger, f"Listo: {new} notas nuevas en el índice · {errors} archivos con error")
        return 1 if errors else 0
    finally:
        await source.aclose()
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de ``python -m app.cli.ingesta_historial``.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Historial de GDELT para el índice local.")
    parser.add_argument("--dias", type=int, default=1, help="Días hacia atrás.")
    parser.add_argument(
        "--descargar", action="store_true", help="Bajar todo lo pendiente (tras la vista previa)."
    )
    args = parser.parse_args(argv)
    retention = settings.news_index_retention_days
    if not 1 <= args.dias <= retention:
        # Más días que la retención se borrarían en la limpieza diaria.
        parser.error(f"--dias debe ser de 1 a {retention} (NEWS_INDEX_RETENTION_DAYS).")
    configure_cli_logging()
    raise SystemExit(asyncio.run(run(args.dias, args.descargar, settings)))


if __name__ == "__main__":
    main()
