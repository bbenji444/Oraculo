"""Comando ``make agrupar-historias``: junta en historias las notas ya guardadas (F12.1c).

Para qué: las búsquedas nuevas agrupan solas al cerrar, pero las notas que
ya estaban guardadas no tienen historia. Este comando recalcula las historias
de **todas** las notas desde cero, en orden de fecha.

Uso:
    ``make agrupar-historias``: **no escribe nada**. Dice cuántas historias
    quedarían y muestra 5 reales (las dos más grandes y tres chicas).
    ``make agrupar-historias ARGS=--aplicar``: muestra lo mismo, pide
    escribir "si" y guarda. Se puede repetir.

No hace: no borra notas (solo cambia ``articles.story_id``; deshacer es
dejarlo en ``NULL``) ni llama a ninguna API (0 créditos, 0 tokens).
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.stories_repository import PostgresStoryStore
from app.adapters.text.similarity import title_similarity, title_token_similarity
from app.application.use_cases.stories import RegroupAllStories, RegroupReport
from app.cli.buscar import CONFIRMATION
from app.core.config import Settings, get_settings
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

TITLE_CHARS = 95
# Notas que se muestran de cada historia de ejemplo.
NOTES_PER_EXAMPLE = 6


def show(report: RegroupReport) -> None:
    """Muestra conteos y ejemplos.

    Args:
        report: Resultado de ``RegroupAllStories``.
    """
    cards = report.scanned - report.grouped + report.stories
    heading(logger, "Historias")
    logger.info(
        f"{report.stories} historias con {report.grouped} de {report.scanned} notas · "
        f"la lista pasaría de {report.scanned} a {cards} tarjetas · "
        f"{report.changed} notas cambian respecto a lo guardado"
    )
    if report.examples:
        heading(logger, f"{len(report.examples)} historias reales")
    for story in report.examples:
        lines = "\n".join(
            f"   {n.published_at:%d/%m %H:%M} {n.title[:TITLE_CHARS]}"
            for n in story[:NOTES_PER_EXAMPLE]
        )
        more = (
            f"\n   … y {len(story) - NOTES_PER_EXAMPLE} más"
            if len(story) > NOTES_PER_EXAMPLE
            else ""
        )
        logger.info(f"[{len(story)} notas]\n{lines}{more}")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Junta en historias las notas guardadas.")
    parser.add_argument("--aplicar", action="store_true", help='guardar (pide escribir "si")')
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
        use_case = RegroupAllStories(
            PostgresStoryStore(engine), title_similarity, title_token_similarity
        )
        preview = await use_case.run(apply=False)
        show(preview)
        if not args.aplicar:
            logger.info(
                'No se escribió nada. Para guardar: make agrupar-historias ARGS="--aplicar"'
            )
            return 0
        if preview.changed == 0:
            logger.info("Las historias ya están al día.")
            return 0
        answer = ask(f'Escribe "{CONFIRMATION}" para guardar {preview.changed} cambios: ')
        if answer.strip().lower() != CONFIRMATION:
            logger.warning("Cancelado: no se escribió nada.")
            return 1
        applied = await use_case.run(apply=True)
        heading(logger, "Historias guardadas")
        logger.info(f"{applied.stories} historias · {applied.changed} notas actualizadas")
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
