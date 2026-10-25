"""Comando ``make reparar-texto``: repara el Mojibake de las notas ya guardadas (F12.1).

Para qué: las notas nuevas ya entran limpias, pero las que llegaron antes
de F12.1 conservan títulos como ``seÃ±alÃ³`` o ``ChihuahuaðŸŽ¦``, y así se
ven en el monitor y en los reportes. Este comando recorre ``news_index``,
``articles`` y ``article_texts`` por lotes y los repara.

Uso:
    ``make reparar-texto``: **no escribe nada**. Dice cuántos renglones
    cambiarían por tabla y muestra 5 ejemplos reales (antes → después).
    ``make reparar-texto ARGS=--aplicar``: muestra lo mismo, pide escribir
    "si" y entonces guarda, con un commit por lote.

No hace: no llama a ninguna API ni a la IA (0 créditos, 0 tokens) y no
borra nada.
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.text_repair_repository import PostgresStoredText
from app.application.ports.text_repair import TEXT_TABLES
from app.application.use_cases.repair_text import SAMPLE_SIZE, RepairReport, RepairStoredText
from app.cli.buscar import CONFIRMATION
from app.core.config import Settings, get_settings
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

# Lo que se muestra de cada texto: suficiente para ver el arreglo sin
# llenar la pantalla con cuerpos de notas completos.
PREVIEW_CHARS = 110


def _excerpt(before: str, after: str) -> tuple[str, str]:
    """Recorte de antes y después alrededor del primer carácter distinto."""
    start = next(
        (i for i, (a, b) in enumerate(zip(before, after, strict=False)) if a != b),
        0,
    )
    begin = max(0, start - PREVIEW_CHARS // 3)
    return before[begin : begin + PREVIEW_CHARS], after[begin : begin + PREVIEW_CHARS]


def show(reports: Sequence[RepairReport]) -> None:
    """Muestra los conteos por tabla y los ejemplos.

    Args:
        reports: Un reporte por tabla.
    """
    heading(logger, "Textos con Mojibake")
    for report in reports:
        logger.info(f"{report.table}: {report.changed} de {report.scanned} renglones cambian")
    examples = [e for r in reports for e in r.examples][:SAMPLE_SIZE]
    if examples:
        heading(logger, f"{len(examples)} ejemplos reales")
    for e in examples:
        before, after = _excerpt(e.before, e.after)
        logger.info(
            f"[{e.table}.{e.column} #{e.row_id}]\n   antes:   {before}\n   después: {after}"
        )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Repara el Mojibake de las notas guardadas.")
    parser.add_argument(
        "--aplicar", action="store_true", help='guardar los cambios (pide escribir "si")'
    )
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
        use_case = RepairStoredText(PostgresStoredText(engine))
        preview = [await use_case.run(table, apply=False) for table in TEXT_TABLES]
        show(preview)
        total = sum(r.changed for r in preview)
        if not args.aplicar:
            logger.info('No se escribió nada. Para guardar: make reparar-texto ARGS="--aplicar"')
            return 0
        if total == 0:
            logger.info("No hay nada que reparar.")
            return 0
        answer = ask(f'Escribe "{CONFIRMATION}" para reparar {total} renglones: ')
        if answer.strip().lower() != CONFIRMATION:
            logger.warning("Cancelado: no se escribió nada.")
            return 1
        applied = [await use_case.run(table, apply=True) for table in TEXT_TABLES]
        heading(logger, "Reparación aplicada")
        for report in applied:
            logger.info(f"{report.table}: {report.changed} renglones reparados")
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
