"""Comando ``make clasificar``: clasifica por categoría (el delito) las notas guardadas (F12.4).

Para qué: las búsquedas nuevas clasifican solas al cerrar, pero las notas
que ya estaban guardadas no tienen categoría. Este comando las clasifica con
la IA en lotes de 25, con título y resumen (nunca el texto, §8).

Uso:
    ``make clasificar``: toma 5 notas de la búsqueda más reciente (o de
    ``--busqueda <id>``), dice cuánto costaría, pide "si", las clasifica y
    las muestra **sin guardar nada** (CLAUDE.md §2.6).
    ``make clasificar ARGS="--notas 1382,1463"``: prueba casos elegidos (las
    que falten por clasificar con la versión vigente), sin guardar.
    ``make clasificar ARGS=--aplicar``: clasifica y guarda todas las notas
    pendientes; antes dice cuántas son y cuánto costaría, y pide "si".

Además de la categoría muestra quién actúa en cada nota y si cuenta para el
concepto FGR (F12.5, ADR-0030).

No hace: no consulta proveedores de noticias (0 créditos) ni cambia el
catálogo de categorías.
"""

import argparse
import asyncio
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.llm.factory import MissingLLMKeyError, build_llm
from app.adapters.persistence.categories_repository import PostgresCategoryStore
from app.adapters.persistence.search_repository import PostgresSearchStore
from app.application.use_cases.classify import (
    BATCH_SIZE,
    SAMPLE_SIZE,
    ClassifyArticles,
    ClassifyReport,
)
from app.cli.buscar import CONFIRMATION
from app.core.config import Settings, get_settings
from app.domain.authority import AUTHORITY_LABEL, FGR_FEDERAL_EXCLUDED, Authority
from app.domain.enrichment import LLMUsage
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

TITLE_CHARS = 90
# Tokens estimados por lote (prompt con el catálogo ~1,000, más ~80 por nota de
# entrada y ~30 por nota de respuesta). Solo para avisar el costo antes.
_PROMPT_TOKENS_PER_BATCH = 1000
_TOKENS_IN_PER_NOTE = 80
_TOKENS_OUT_PER_NOTE = 30


def estimated_usage(notes: int) -> LLMUsage:
    """Tokens que costaría clasificar ``notes`` notas, para avisar antes de gastar.

    Args:
        notes: Cuántas notas.

    Returns:
        La estimación, redondeada por arriba a lotes completos.
    """
    batches = -(-notes // BATCH_SIZE)
    return LLMUsage(
        batches * _PROMPT_TOKENS_PER_BATCH + notes * _TOKENS_IN_PER_NOTE,
        notes * _TOKENS_OUT_PER_NOTE,
    )


def authority_text(authority: Authority | None) -> str:
    """Quién actúa, en palabras, y si la nota cuenta para el concepto FGR (ADR-0030).

    Args:
        authority: Lo que respondió la IA.

    Returns:
        Por ejemplo «Fiscalía estatal (no cuenta para la FGR)».
    """
    if authority is None:
        return "quién actúa: sin respuesta"
    suffix = " (no cuenta para la FGR)" if authority in FGR_FEDERAL_EXCLUDED else ""
    return f"{AUTHORITY_LABEL[authority]}{suffix}"


def show(
    report: ClassifyReport,
    prices: tuple[float, float],
    *,
    saved: bool,
    shown: int = SAMPLE_SIZE,
) -> None:
    """Muestra lo que se eligió, el reparto por categoría y quién actúa, y el costo real.

    Args:
        report: Resultado de la clasificación.
        prices: Dólares por millón de tokens (entrada, salida).
        saved: Si se guardó.
        shown: Cuántas notas mostrar una por una (las elegidas con ``--notas``
            se muestran todas).
    """
    suffix = "" if saved else " (sin guardar)"
    heading(logger, f"{report.classified} notas clasificadas{suffix}")
    for choice in report.choices[:shown]:
        note = report.notes.get(choice.article_id)
        title = note.title[:TITLE_CHARS] if note else f"nota {choice.article_id}"
        logger.info(
            f"[{choice.article_id}] {title}\n   → {choice.category.name} · "
            f"«{choice.raw_label or '—'}» · {authority_text(choice.authority)}"
        )
    if len(report.choices) > shown:
        heading(logger, "Reparto por categoría")
        for name, count in Counter(c.category.name for c in report.choices).most_common():
            logger.info(f"{count:>4}  {name}")
        heading(logger, "Quién actúa")
        for authority, count in Counter(
            authority_text(c.authority) for c in report.choices
        ).most_common():
            logger.info(f"{count:>4}  {authority}")
    cost = report.usage.cost_usd(*prices)
    logger.info(
        f"IA: {report.usage.tokens_in} tokens de entrada y {report.usage.tokens_out} de salida, "
        f"~{cost:.4f} USD"
    )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Clasifica por categoría las notas guardadas.")
    parser.add_argument("--busqueda", type=UUID, help="de dónde tomar los 5 ejemplos")
    parser.add_argument(
        "--notas",
        type=_note_ids,
        help=f"ids separados por coma para probar casos (máx. {BATCH_SIZE}); no guarda",
    )
    parser.add_argument(
        "--aplicar", action="store_true", help='clasificar y guardar todas (pide "si")'
    )
    args = parser.parse_args(argv)
    if args.aplicar and args.notas:
        parser.error("--notas solo prueba, sin guardar; no se combina con --aplicar.")
    return args


def _note_ids(value: str) -> list[int]:
    try:
        ids = [int(part) for part in value.split(",") if part.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError("Escribe ids de notas separados por coma.") from error
    if not ids or len(ids) > BATCH_SIZE:
        raise argparse.ArgumentTypeError(f"Escribe de 1 a {BATCH_SIZE} ids de notas.")
    return ids


async def _sample_ids(
    args: argparse.Namespace, store: PostgresCategoryStore, engine_store: PostgresSearchStore
) -> tuple[list[int] | None, str]:
    search_id = args.busqueda or await engine_store.last_search_id()
    if search_id is None:
        return None, "las primeras notas pendientes"
    return await store.search_article_ids(search_id), f"la búsqueda {search_id}"


async def run(
    args: argparse.Namespace, settings: Settings, ask: Callable[[str], str] = input
) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.
        ask: Función para pedir confirmación.

    Returns:
        Código de salida: 0 bien; 1 si se canceló, falta la llave o no hay notas.
    """
    try:
        llm = build_llm(settings)
    except MissingLLMKeyError as error:
        logger.error(f"{error} Pégala en .env y vuelve a intentar.")
        return 1
    if llm.classifier is None:
        logger.error("La IA configurada no sabe clasificar.")
        return 1
    engine = create_async_engine(settings.database_url())
    prices = (llm.price_input_per_million, llm.price_output_per_million)
    try:
        store = PostgresCategoryStore(engine)
        use_case = ClassifyArticles(store, llm.classifier)
        ids: list[int] | None = None
        shown = SAMPLE_SIZE
        if args.aplicar:
            pending = await store.count_pending(use_case.version)
            what = f"{pending} notas pendientes; se guardan"
        elif args.notas:
            ids = args.notas
            pending = shown = len(await store.pending_notes(ids, use_case.version))
            what = f"{pending} de las {len(ids)} notas elegidas; no se guarda nada"
        else:
            ids, source = await _sample_ids(args, store, PostgresSearchStore(engine))
            available = (
                len(await store.pending_notes(ids, use_case.version))
                if ids is not None
                else SAMPLE_SIZE
            )
            pending = min(SAMPLE_SIZE, available)
            what = f"{pending} notas de ejemplo de {source}; no se guarda nada"
        if pending == 0:
            logger.info("No hay notas por clasificar.")
            return 1
        estimate = estimated_usage(pending).cost_usd(*prices)
        heading(logger, "Clasificar por categoría (todavía no se ha gastado nada)")
        logger.info(f"{what} · IA: {llm.provider} · ~{estimate:.4f} USD · 0 créditos")
        if ask(f'Escribe "{CONFIRMATION}" para clasificar: ').strip().lower() != CONFIRMATION:
            logger.warning("Cancelado: no se gastó nada.")
            return 1
        if args.aplicar:
            show(await use_case.run_pending(), prices, saved=True)
        else:
            show(await use_case.sample(ids, size=shown), prices, saved=False, shown=shown)
        return 0
    finally:
        await llm.llm.aclose()
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
