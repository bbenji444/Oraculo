"""Comando ``make extraer-entidades``: la IA lee notas de un caso y propone sus entidades.

Para qué (Fase 9.4, CLAUDE.md §2.6): ver ejemplos reales antes de procesar
todo. Toma las notas del caso que faltan por leer (por defecto 5), muestra el
costo estimado y pide escribir "si". Luego enseña, nota por nota, cada entidad
propuesta con su tipo, su estatus legal según la nota y su cita, y lo que se
descartó por no estar escrito en la nota.

Hace exactamente lo mismo que el worker (``app.worker.entity_jobs``), pero
aquí mismo y a la vista: las sugerencias quedan en el caso para revisarlas en
la pestaña Casos.

Uso:
    ``make extraer-entidades`` (el caso más reciente, 5 notas),
    ``make extraer-entidades ARGS="--caso <id>"`` o
    ``make extraer-entidades ARGS="--caso <id> --muestra 8"``.

No hace: no gasta créditos de SearchApi ni confirma nada (eso lo hace una
persona en la pantalla).
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.llm.factory import MissingLLMKeyError, build_entity_extractor
from app.adapters.persistence.cases_repository import PostgresCaseRepository
from app.adapters.persistence.entities_repository import PostgresEntityRepository
from app.application.audit import Actor
from app.application.use_cases.cases import DEFAULT_STATUSES
from app.application.use_cases.entities import (
    ExtractCaseArticle,
    ExtractionOutcome,
    estimate_cost,
)
from app.cli.buscar import CONFIRMATION
from app.core.config import Settings, get_settings
from app.domain.entity_extraction import CASE_EXTRACTION_MAX_ARTICLES, REJECTION_LABEL, TextSource
from app.domain.geocoding import MentionRole
from app.domain.investigation import ENTITY_TYPE_LABEL, LEGAL_STATUS_LABEL
from app.geodata.consola import configure_cli_logging, heading
from app.worker.entity_jobs import prices_of

logger = logging.getLogger(__name__)

# CLAUDE.md §2.6: 5 ejemplos reales antes de procesar todo.
DEFAULT_SAMPLE = 5
TITLE_CHARS = 90
_ROLE = {MentionRole.EVENT: "en el hecho", MentionRole.MENTIONED: "solo se nombra"}
_SOURCE = {
    TextSource.FULL_TEXT: "texto completo",
    TextSource.TITLE_SNIPPET: "solo título y fragmento (el texto ya se borró)",
}


def show(position: str, title: str, outcome: ExtractionOutcome | None) -> None:
    """Muestra lo que propuso la IA de una nota.

    Args:
        position: "[2/5]".
        title: Título de la nota.
        outcome: Resultado de ``ExtractCaseArticle``.
    """
    heading(logger, f"{position} {title[:TITLE_CHARS]}")
    if outcome is None:
        logger.info("   Nada que hacer: ya se había leído o ya no está en el caso.")
        return
    if outcome.extraction is None:
        logger.warning(f"   {outcome.status.value}: {outcome.error or 'fuera del tope del caso'}")
        return
    extraction = outcome.extraction
    spent = (
        "reutilizada, sin costo"
        if outcome.reused
        else f"{outcome.usage.tokens_in:,} tokens de entrada y {outcome.usage.tokens_out:,} "
        f"de salida · {outcome.cost_usd:.5f} USD"
    )
    logger.info(f"   {_SOURCE[extraction.source]} · {spent}")
    for p in extraction.reviewed.proposals:
        legal = f" · {LEGAL_STATUS_LABEL[p.legal_status_hint]}" if p.legal_status_hint else ""
        aliases = f" · alias: {', '.join(p.aliases)}" if p.aliases else ""
        logger.info(
            f"   + {ENTITY_TYPE_LABEL[p.type]}: {p.label}{legal} · {_ROLE[p.role]} · "
            f"confianza {p.confidence:.2f}{aliases}\n"
            f"       «{p.evidence_span}»"
        )
    for r in extraction.reviewed.rejected:
        logger.info(f"   – descartada: {r.label} ({r.type}) — {REJECTION_LABEL[r.reason]}")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(
        description="La IA lee notas de un caso y propone sus entidades."
    )
    parser.add_argument("--caso", type=UUID, help="id del caso (por defecto, el más reciente)")
    parser.add_argument(
        "--muestra",
        type=int,
        default=DEFAULT_SAMPLE,
        help=f"cuántas notas pendientes leer (por defecto {DEFAULT_SAMPLE})",
    )
    return parser.parse_args(argv)


async def run(
    args: argparse.Namespace, settings: Settings, ask: Callable[[str], str] = input
) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.
        ask: Función para pedir confirmación antes de gastar.

    Returns:
        Código de salida: 0 bien; 1 si no hay caso, falta la llave o se canceló.
    """
    try:
        setup = build_entity_extractor(settings)
    except MissingLLMKeyError as error:
        logger.error(f"{error} Pégala en .env y vuelve a intentar.")
        return 1
    engine = create_async_engine(settings.database_url())
    try:
        cases = PostgresCaseRepository(engine)
        entities = PostgresEntityRepository(engine)
        user = settings.dev_user
        case_id = args.caso
        if case_id is None:
            latest = await cases.list_for_user(user, DEFAULT_STATUSES, None, None, 1)
            case_id = latest[0].case.id if latest else None
        view = await cases.get_view(case_id, user) if case_id else None
        if case_id is None or view is None:
            logger.error("No hay ese caso (o no eres miembro). Crea uno en la pestaña Casos.")
            return 1
        room = max(CASE_EXTRACTION_MAX_ARTICLES - await entities.done_count(case_id), 0)
        article_ids = await entities.to_analyze(case_id, min(args.muestra, room))
        analysis = await entities.analysis(case_id)
        heading(logger, f"Caso «{view.case.name}» (todavía no se ha gastado nada)")
        if not article_ids:
            logger.info(f"No hay notas por leer: {analysis.done} de {analysis.articles} leídas.")
            return 0
        prices = prices_of(setup)
        logger.info(
            f"La IA leerá {len(article_ids)} de {analysis.pending + analysis.failed} notas "
            f"pendientes · IA: {setup.provider} · {setup.extractor.model} · "
            f"~{estimate_cost(len(article_ids), prices):.4f} USD · 0 créditos de SearchApi"
        )
        if ask(f'Escribe "{CONFIRMATION}" para leerlas: ').strip().lower() != CONFIRMATION:
            logger.warning("Cancelado: no se gastó nada.")
            return 1
        use_case = ExtractCaseArticle(entities, setup.extractor, prices)
        actor = Actor(user)
        total = 0.0
        for number, article_id in enumerate(article_ids, start=1):
            source = await entities.article_source(case_id, article_id)
            outcome = await use_case.execute(case_id, article_id, actor)
            total += outcome.cost_usd if outcome else 0.0
            title = source.title if source else f"Nota {article_id}"
            show(f"[{number}/{len(article_ids)}]", title, outcome)
        heading(logger, f"Listo: {total:.5f} USD en total")
        logger.info("Revisa las sugerencias en la pestaña Casos; ahí se confirman o descartan.")
        return 0
    finally:
        await setup.extractor.aclose()
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
