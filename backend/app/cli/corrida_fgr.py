"""Comando ``make corrida-fgr``: corre ahora una corrida del monitor FGR (F12.8).

Hace exactamente lo que el reloj hace a las 07:00, 15:00 y 23:00 (ADR-0031):
busca a la FGR en todo México, solo lo publicado desde la corrida programada
anterior, con Google News RSS y el índice local; la guarda como corrida automática y deja su PDF en
``REPORTS_DIR``. Sirve para probar el monitor sin esperar al horario.

Antes de correr muestra qué buscaría y cuánto costaría (0 créditos; centavos
de la IA por las notas nuevas) y pide "si". Al final enseña 5 notas reales.

No hace: no cambia los horarios ni usa SearchApi.
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.search_repository import PostgresArticleStore
from app.cli.buscar import CONFIRMATION
from app.core.config import Settings, get_settings
from app.geodata.consola import configure_cli_logging, heading
from app.worker.automatic_jobs import run_automatic_job

logger = logging.getLogger(__name__)

# Notas de ejemplo al final (CLAUDE.md §2.6).
SAMPLE = 5
TITLE_CHARS = 90


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando (no tiene: el perfil es fijo).

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    return argparse.ArgumentParser(
        description="Corre ahora una corrida del monitor automático FGR."
    ).parse_args(argv)


async def run(settings: Settings, ask: Callable[[str], str] = input) -> int:
    """Flujo completo del comando.

    Args:
        settings: Configuración.
        ask: Función para pedir confirmación.

    Returns:
        0 bien; 1 si se canceló.
    """
    heading(logger, "Corrida del monitor FGR (todavía no se ha gastado nada)")
    logger.info(
        f"Concepto: {settings.automatic_concept} · región: {settings.automatic_region_code} · "
        "solo lo publicado desde la corrida anterior · "
        f"fuentes: {settings.automatic_sources}"
    )
    logger.info("0 créditos de SearchApi; la IA solo lee las notas que no ha visto.")
    if ask(f'Escribe "{CONFIRMATION}" para correrla: ').strip().lower() != CONFIRMATION:
        logger.warning("Cancelado: no se gastó nada.")
        return 1
    summary = await run_automatic_job(settings)
    report = summary.report
    heading(
        logger, f"Corrida de las {summary.scheduled_for:%H:%M} del {summary.scheduled_for:%d/%m}"
    )
    logger.info(
        f"{report.status.value} · {report.articles} notas · {report.in_region} en México · "
        f"{report.credits_used} créditos · IA ~{report.llm_cost_usd:.4f} USD"
    )
    logger.info(f"Búsqueda: {summary.search_id}")
    logger.info(f"PDF: {summary.pdf_path or 'no se pudo armar (ver logs)'}")
    engine = create_async_engine(settings.database_url())
    try:
        preview = await PostgresArticleStore(engine).preview(summary.search_id, SAMPLE)
    finally:
        await engine.dispose()
    heading(logger, f"{len(preview)} notas de ejemplo")
    for note in preview:
        concepts = ", ".join(note.concepts) or "no relevante"
        logger.info(f"{note.title[:TITLE_CHARS]}\n   {note.place or 'sin ubicación'} · {concepts}")
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    parse_args(argv)
    configure_cli_logging()
    raise SystemExit(asyncio.run(run(get_settings())))


if __name__ == "__main__":
    main()
