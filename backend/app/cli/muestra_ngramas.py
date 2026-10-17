"""Comando ``make ngramas-muestra``: prueba real de los ngramas de GDELT (ADR-0014).

Antes de encender los ngramas en la ingesta automática, Benji ve con datos
reales qué entra y cuánto cuesta (CLAUDE.md §2.6). El comando procesa los
últimos ``MINUTOS`` (60 por defecto) igual que lo haría el reloj de Celery, y
muestra:

- archivos, megas descargados, notas leídas y notas guardadas;
- 5 ejemplos reales (título, medio, fecha, link y cuántas frases del cuerpo);
- cuánto ocupan en disco las notas de ngramas y la proyección a un día.

Las notas quedan guardadas en el índice: son datos reales de prueba.

Uso: ``make ngramas-muestra`` o ``make ngramas-muestra MINUTOS=30``

No hace: no enciende ``GDELT_NGRAMS_ENABLED``; eso lo decide Benji.
"""

import argparse
import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.ingest.factory import build_ngrams_source
from app.adapters.persistence.news_index_repository import (
    PostgresIngestRunLog,
    PostgresNewsIndex,
    index_stats,
)
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.application.clock import MEXICO_CITY
from app.application.use_cases.ingest import IngestGdeltNgrams, IngestReport, recent_minutes
from app.core.config import Settings, get_settings
from app.domain.news_index import BODY_SEPARATOR, GDELT_NGRAMS_SOURCE
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024
_MINUTES_PER_DAY = 24 * 60
DEFAULT_MINUTES = 60
EXAMPLES = 5


def _show_examples(reports: Sequence[IngestReport]) -> None:
    examples = [item for report in reports for item in report.sample][:EXAMPLES]
    heading(logger, f"{len(examples)} ejemplos reales")
    for number, item in enumerate(examples, start=1):
        local = item.published_at.astimezone(MEXICO_CITY).strftime("%d/%m/%Y %H:%M")
        phrases = len((item.body_terms or "").split(BODY_SEPARATOR))
        logger.info(f"{number}. {item.title}")
        logger.info(f"   {item.source_domain} · {local} · {phrases} frases del cuerpo")
        logger.info(f"   {item.url}")


async def run(minutes: int, settings: Settings) -> int:
    """Procesa los últimos minutos y muestra consumo, espacio y ejemplos.

    Args:
        minutes: Cuántos minutos hacia atrás.
        settings: Configuración.

    Returns:
        0 si todo salió bien; 1 si algún minuto falló.
    """
    engine = create_async_engine(settings.database_url())
    terms = await PostgresRegionRepository(engine).state_terms()
    source = build_ngrams_source(settings, terms)
    try:
        heading(logger, f"Ngramas de GDELT · últimos {minutes} minutos")
        logger.info(f"Reconociendo México por {len(terms)} nombres y términos de estados")
        moments = recent_minutes(datetime.now(UTC), minutes, settings.ngrams_delay_minutes)
        use_case = IngestGdeltNgrams(
            source, PostgresNewsIndex(engine), PostgresIngestRunLog(engine)
        )
        reports = await use_case.run(moments)
        downloaded = sum(report.bytes_downloaded for report in reports)
        errors = [report for report in reports if report.status == "error"]
        logger.info(
            f"{len(reports)} minutos con archivos · {downloaded / _BYTES_PER_MB:.1f} MB · "
            f"{sum(r.items_seen for r in reports):,} notas leídas · "
            f"{sum(r.items_kept for r in reports)} en español sobre México · "
            f"{sum(r.items_new for r in reports)} nuevas"
        )
        for report in errors:
            logger.warning(f"{report.item}: {report.message}")
        _show_examples(reports)
        stats, total_bytes = await index_stats(engine)
        heading(logger, "Espacio en disco")
        for stat in stats:
            logger.info(
                f"{stat.source}: {stat.notes:,} notas · frases del cuerpo "
                f"{stat.body_bytes / _BYTES_PER_MB:.1f} MB en {stat.with_body:,} notas"
            )
        logger.info(
            f"Tabla news_index completa (con índices): {total_bytes / _BYTES_PER_MB:.1f} MB"
        )
        ngrams = next((s for s in stats if s.source == GDELT_NGRAMS_SOURCE), None)
        if ngrams is not None and reports:
            factor = _MINUTES_PER_DAY / minutes
            daily_download = downloaded * factor / _BYTES_PER_MB
            daily_body = ngrams.body_bytes * factor / _BYTES_PER_MB
            logger.info(
                f"Proyección a un día (×{factor:.0f}): ~{daily_download:,.0f} MB de descarga "
                f"y ~{daily_body:,.0f} MB de frases en disco (sin contar índices)"
            )
        return 1 if errors else 0
    finally:
        await source.aclose()
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de ``python -m app.cli.muestra_ngramas``.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    parser = argparse.ArgumentParser(description="Prueba real de los ngramas de GDELT.")
    parser.add_argument("--minutos", type=int, default=DEFAULT_MINUTES)
    args = parser.parse_args(argv)
    if args.minutos < 1:
        parser.error("--minutos debe ser al menos 1.")
    configure_cli_logging()
    raise SystemExit(asyncio.run(run(args.minutos, get_settings())))


if __name__ == "__main__":
    main()
