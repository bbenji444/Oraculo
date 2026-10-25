"""Comando ``make limpiar-duplicados``: quita del índice local las notas repetidas (F12.1b).

Para qué: antes de F12.1b el índice guardaba la misma nota varias veces (la
misma URL con ``:443``, títulos de portada repetidos, «notas» que eran solo
un emoji). Desde F12.1b ya no entran; este comando quita las que ya estaban.

Uso:
    ``make limpiar-duplicados``: **no escribe nada**. Dice cuántas notas
    sobran por motivo y muestra 5 ejemplos reales (qué se borra y qué se
    queda en su lugar).
    ``make limpiar-duplicados ARGS=--aplicar``: muestra lo mismo, pide
    escribir "si" y entonces borra, por lotes. Haz antes ``make db-dump``.

No hace: no toca ``articles``, casos ni reportes; no llama a ninguna API
(0 créditos, 0 tokens).
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.news_index_repository import PostgresIndexCleanup
from app.application.use_cases.clean_duplicates import CleanIndexDuplicates, CleanupReport
from app.cli.buscar import CONFIRMATION
from app.core.config import Settings, get_settings
from app.domain.index_cleanup import CleanupReason
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

TITLE_CHARS = 80
_REASON: dict[CleanupReason, str] = {
    "sin_letras": "título sin letras",
    "misma_url": "la misma URL con otra forma",
    "mismo_medio": "el mismo medio con el mismo texto",
}


def show(report: CleanupReport) -> None:
    """Muestra conteos y ejemplos.

    Args:
        report: Resultado de ``CleanIndexDuplicates``.
    """
    heading(logger, f"Índice local: sobran {report.removed} de {report.scanned} notas")
    for reason, label in _REASON.items():
        logger.info(f"{label}: {report.by_reason.get(reason, 0)}")
    logger.info(f"huellas de URL por actualizar: {report.rehashed}")
    if report.examples:
        heading(logger, f"{len(report.examples)} ejemplos reales")
    for r in report.examples:
        kept = (
            f"\n   se queda: #{r.kept.note_id} {r.kept.url}"
            if r.kept
            else "\n   (no queda ninguna en su lugar)"
        )
        logger.info(
            f"[{_REASON[r.reason]}] {r.note.title[:TITLE_CHARS]}\n"
            f"   se borra: #{r.note.note_id} {r.note.url}{kept}"
        )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Quita notas repetidas del índice local.")
    parser.add_argument("--aplicar", action="store_true", help='borrar (pide escribir "si")')
    return parser.parse_args(argv)


async def run(
    args: argparse.Namespace, settings: Settings, ask: Callable[[str], str] = input
) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.
        ask: Función para pedir confirmación (solo con ``--aplicar``).

    Returns:
        Código de salida: 0 bien; 1 si se canceló.
    """
    engine = create_async_engine(settings.database_url())
    try:
        use_case = CleanIndexDuplicates(PostgresIndexCleanup(engine))
        preview = await use_case.run(apply=False)
        show(preview)
        if not args.aplicar:
            logger.info('No se borró nada. Para aplicar: make limpiar-duplicados ARGS="--aplicar"')
            return 0
        if preview.removed == 0 and preview.rehashed == 0:
            logger.info("No hay nada que limpiar.")
            return 0
        answer = ask(f'Escribe "{CONFIRMATION}" para borrar {preview.removed} notas del índice: ')
        if answer.strip().lower() != CONFIRMATION:
            logger.warning("Cancelado: no se borró nada.")
            return 1
        applied = await use_case.run(apply=True)
        heading(logger, "Limpieza aplicada")
        logger.info(f"{applied.removed} notas borradas · {applied.rehashed} huellas actualizadas")
        return 0
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    args = parse_args(argv)
    configure_cli_logging()
    raise SystemExit(asyncio.run(run(args, get_settings())))


if __name__ == "__main__":
    main()
