"""Comando ``make revisar-relevancia``: cómo quedó la relevancia de una búsqueda (ADR-0114).

Para qué: medir la relevancia estricta en búsquedas reales y compararla con
Google sin volver a gastar. Muestra:

1. el pedido: lo que escribió el analista, sus frases, los términos
   obligatorios («Debe hablar de») y la región;
2. los contadores del avance: lo que se tiró antes de la IA (fuera del
   periodo, sin la palabra de la subdivisión, sin lo pedido con sus títulos
   de muestra) y lo que se quedó sin juicio por el tope;
3. cuántas notas hay en cada banda (relevante, por confirmar, cercana,
   ajena, sin juicio) y cuántas caen fuera de la región;
4. una fila por nota: banda | puntaje | región | texto | proveedores |
   título | razón, de la banda más alta a la más baja.

Uso:
    ``make revisar-relevancia`` (la búsqueda más reciente) o
    ``make revisar-relevancia ARGS="--busqueda <id>"``.

Usa la configuración de siempre (``.env``): la base de desarrollo, salvo que
``POSTGRES_DB`` diga otra. La conexión se abre en **solo lectura**
(``default_transaction_read_only``): aunque hubiera un error, no puede
escribir nada.

No hace: no escribe, no llama a la IA ni a los proveedores (0 créditos, 0 tokens).
"""

import argparse
import asyncio
import logging
from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.application.ports.relevance_review import (
    SearchArticlesReaderPort,
    SearchCopyReaderPort,
)
from app.application.ports.search_store import SearchConcept
from app.application.use_cases.review_relevance import (
    RelevanceReview,
    ReviewRelevance,
    ReviewRow,
)
from app.application.use_cases.run_search import SearchNotFoundError
from app.core.config import Settings, get_settings
from app.domain.authority import RelevanceBand
from app.domain.concept import QueryMode
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

# Toda transacción de esta conexión es de solo lectura (opción de libpq que
# acepta psycopg): PostgreSQL rechaza cualquier INSERT, UPDATE o DELETE.
READ_ONLY_OPTIONS = "-c default_transaction_read_only=on"
# Lo que cabe de título y razón en una fila de terminal ancha (se fijó en
# 70 y 140 caracteres; decisión del 18/11/2026, ADR-0114).
TITLE_CHARS = 70
REASON_CHARS = 140
# Ancho de la columna de banda: «por confirmar» es la etiqueta más larga.
BAND_WIDTH = 13
EXTRACTION_WIDTH = 8
REGION_WIDTH = 6
PROVIDERS_WIDTH = 30
NO_VALUE = "—"
BAND_LABEL: dict[RelevanceBand | None, str] = {
    RelevanceBand.RELEVANT: "relevante",
    RelevanceBand.UNCONFIRMED: "por confirmar",
    RelevanceBand.RELATED: "cercana",
    RelevanceBand.UNRELATED: "ajena",
    None: "sin juicio",
}
BAND_PLURAL: dict[RelevanceBand | None, str] = {
    RelevanceBand.RELEVANT: "relevantes",
    RelevanceBand.UNCONFIRMED: "por confirmar",
    RelevanceBand.RELATED: "cercanas",
    RelevanceBand.UNRELATED: "ajenas",
    None: "sin juicio",
}
REGION_LABEL: dict[bool | None, str] = {True: "dentro", False: "FUERA", None: NO_VALUE}
# Contadores del avance de ``RunSearch`` (``searches.progress``) con su
# nombre en pantalla, en el orden en que pasan las notas.
PROGRESS_LABELS: dict[str, str] = {
    "outside_window": "fuera del periodo",
    "off_topic": "sin la palabra de la subdivisión",
    "off_core": "sin lo pedido (filtro de palabras)",
    "articles": "notas distintas",
    "known": "ya guardadas de antes",
    "reused": "reutilizadas sin pagar",
    "skipped_by_cap": "sin juicio por el tope",
    "fallback": "solo título y fragmento",
    "enriched": "juzgadas por la IA",
    "older_event": "hecho de otros días",
    "in_region": "dentro de la región",
    "out_of_region": "fuera de la región",
    "unlocated": "sin ubicación",
}
OFF_CORE_SAMPLES_KEY = "off_core_samples"


def _cut(text: str | None, size: int) -> str:
    if not text:
        return NO_VALUE
    clean = " ".join(text.split())
    return clean if len(clean) <= size else clean[: size - 1] + "…"


def concept_lines(concept: SearchConcept) -> list[str]:
    """Lo que pidió el analista en un concepto.

    Args:
        concept: Concepto copiado en la búsqueda.

    Returns:
        Líneas para la pantalla.
    """
    mode = "como en Google" if concept.query_mode is QueryMode.OPEN else "frases exactas"
    return [
        f"Concepto «{concept.name}» ({mode})",
        f"  Pidió: {concept.description or NO_VALUE}",
        f"  Frases: {' | '.join(concept.keywords) or NO_VALUE}",
        f"  Debe hablar de: {', '.join(concept.required_terms) or NO_VALUE}",
    ]


def progress_lines(progress: Mapping[str, object]) -> list[str]:
    """Los contadores del avance, con su nombre, y los títulos descartados de muestra.

    Args:
        progress: ``searches.progress``.

    Returns:
        Líneas para la pantalla.
    """
    counts = [
        f"{label}: {progress[key]}" for key, label in PROGRESS_LABELS.items() if key in progress
    ]
    lines = ["Avance: " + (" · ".join(counts) or "sin contadores")]
    samples = progress.get(OFF_CORE_SAMPLES_KEY)
    if isinstance(samples, list) and samples:
        lines.append("  Descartadas sin lo pedido (muestra):")
        lines.extend(f"   - {_cut(str(title), TITLE_CHARS)}" for title in samples)
    return lines


def row_line(row: ReviewRow) -> str:
    """Una nota en una línea: banda | puntaje | región | texto | proveedores | título | razón.

    Args:
        row: Fila de la revisión.

    Returns:
        La línea.
    """
    score = f"{row.score:.2f}" if row.score is not None else NO_VALUE
    providers = _cut(", ".join(dict.fromkeys(row.providers)), PROVIDERS_WIDTH)
    return " | ".join(
        (
            f"{BAND_LABEL[row.band]:<{BAND_WIDTH}}",
            f"{score:>5}",
            f"{REGION_LABEL[row.in_region]:<{REGION_WIDTH}}",
            f"{row.extraction_status:<{EXTRACTION_WIDTH}}",
            f"{providers:<{PROVIDERS_WIDTH}}",
            _cut(row.title, TITLE_CHARS),
            _cut(row.reason, REASON_CHARS),
        )
    )


def render(review: RelevanceReview) -> list[str]:
    """Toda la revisión como líneas de texto.

    Args:
        review: Revisión armada por ``ReviewRelevance``.

    Returns:
        Líneas para la pantalla, en orden.
    """
    detail = review.detail
    lines = [
        f"Búsqueda {detail.search_id} · Región: {detail.region_name} · "
        f"{detail.date_from:%d/%m/%Y} a {detail.date_to:%d/%m/%Y}",
    ]
    for concept in review.concepts:
        lines.extend(concept_lines(concept))
    lines.extend(progress_lines(review.progress))
    counts = review.band_counts()
    lines.append(
        "Bandas: "
        + " · ".join(f"{BAND_PLURAL[band]} {n}" for band, n in counts.items())
        + f" · fuera de la región {review.outside_region()}"
    )
    lines.append(
        " | ".join(
            (
                f"{'banda':<{BAND_WIDTH}}",
                f"{'score':>5}",
                f"{'región':<{REGION_WIDTH}}",
                f"{'texto':<{EXTRACTION_WIDTH}}",
                f"{'proveedores':<{PROVIDERS_WIDTH}}",
                "título",
                "razón",
            )
        )
    )
    lines.extend(row_line(r) for r in review.rows)
    return lines


async def show_review(
    search_id: UUID | None,
    searches: SearchCopyReaderPort,
    articles: SearchArticlesReaderPort,
) -> int:
    """Arma la revisión y la muestra.

    Args:
        search_id: Búsqueda; ``None`` = la más reciente.
        searches: La búsqueda copiada y su avance.
        articles: Sus notas.

    Returns:
        Código de salida: 0 bien; 1 si no hay búsqueda.
    """
    try:
        review = await ReviewRelevance(searches, articles).execute(search_id)
    except SearchNotFoundError as error:
        logger.error(f"{error.message} Revisa el id o corre primero una búsqueda.")
        return 1
    heading(logger, "Relevancia de la búsqueda (solo lectura: no se gasta ni se escribe nada)")
    for line in render(review):
        logger.info(line)
    return 0


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(
        description="Muestra cómo quedó la relevancia de una búsqueda, sin escribir nada."
    )
    parser.add_argument("--busqueda", type=UUID, help="id de la búsqueda (por defecto, la última)")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, settings: Settings) -> int:
    """Flujo completo del comando, con una conexión de solo lectura.

    Args:
        args: Opciones.
        settings: Configuración (``.env``).

    Returns:
        Código de salida.
    """
    engine = create_async_engine(
        settings.database_url(), connect_args={"options": READ_ONLY_OPTIONS}
    )
    try:
        return await show_review(
            args.busqueda, PostgresSearchStore(engine), PostgresArticleStore(engine)
        )
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
