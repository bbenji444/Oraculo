"""Comando ``make reubicar``: vuelve a ubicar las notas de una búsqueda sin pagar a la IA.

Para qué: después de corregir el geolocalizador o el catálogo (alias
nuevos, reglas nuevas), ver el efecto en una búsqueda real sin volver a
consultar proveedores ni a la IA. Muestra, nota por nota, la ubicación
principal antes y después, y los conteos de dentro, fuera y sin ubicación.

Con ``--con-ia`` además vuelve a pasar por la IA el texto guardado de cada
nota (sirve cuando cambia el prompt o faltan datos que antes no se
guardaban, como las pistas de lugar). Antes de gastar muestra el costo
estimado y pide escribir "si". Nunca consulta proveedores: 0 créditos.

Uso:
    ``make reubicar`` (la búsqueda más reciente),
    ``make reubicar ARGS="--busqueda <id>"`` o
    ``make reubicar ARGS="--con-ia"``.

No hace: no gasta créditos de SearchApi; sin ``--con-ia`` tampoco tokens.
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.adapters.llm.factory import MissingLLMKeyError, build_llm
from app.adapters.persistence.gazetteer_repository import PostgresGazetteer
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.relocate import RelocateSearch, Relocation, ReprocessSearch
from app.application.use_cases.run_search import PipelineLimits
from app.cli.buscar import CONFIRMATION
from app.core.config import Settings, get_settings
from app.domain.enrichment import estimated_usage
from app.domain.geocoding import Place
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

TITLE_CHARS = 60
_REGION = {True: "dentro", False: "FUERA", None: "—"}


def describe(place: Place | None) -> str:
    """Lugar con su clave, o "Sin ubicación".

    Args:
        place: Ubicación principal.

    Returns:
        Texto para la pantalla ("Municipio Guadalajara [14039]").
    """
    return f"{place.display_name} [{place.code}]" if place else "Sin ubicación"


def show(relocations: Sequence[Relocation]) -> None:
    """Muestra el antes y después.

    Args:
        relocations: Resultado de ``RelocateSearch``.
    """
    changed = [r for r in relocations if r.changed]
    heading(logger, f"{len(changed)} de {len(relocations)} notas cambiaron de ubicación")
    for r in changed:
        logger.info(
            f"{r.title[:TITLE_CHARS]}\n"
            f"   antes:   {describe(r.before)}\n"
            f"   después: {describe(r.after)} · {_REGION[r.in_region]} de la región"
        )
    counts = {
        label: sum(1 for r in relocations if r.in_region is value)
        for value, label in ((True, "dentro"), (False, "fuera"), (None, "sin ubicación"))
    }
    logger.info(" · ".join(f"{label}: {n}" for label, n in counts.items()))


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Vuelve a ubicar las notas de una búsqueda.")
    parser.add_argument("--busqueda", type=UUID, help="id de la búsqueda (por defecto, la última)")
    parser.add_argument(
        "--con-ia", action="store_true", help="volver a pasar el texto guardado por la IA"
    )
    return parser.parse_args(argv)


async def run(
    args: argparse.Namespace, settings: Settings, ask: Callable[[str], str] = input
) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.
        ask: Función para pedir confirmación (solo con ``--con-ia``).

    Returns:
        Código de salida: 0 bien; 1 si no hay búsqueda, falta la llave o se canceló.
    """
    engine = create_async_engine(settings.database_url())
    try:
        searches = PostgresSearchStore(engine)
        search_id = args.busqueda or await searches.last_search_id()
        if search_id is None:
            logger.error("No hay búsquedas todavía. Corre primero `make buscar`.")
            return 1
        gazetteer = PostgresGazetteer(engine)
        logger.info(f"Búsqueda {search_id}")
        if args.con_ia:
            return await _reprocess(search_id, settings, engine, ask)
        use_case = RelocateSearch(
            searches,
            PostgresArticleStore(engine),
            gazetteer,
            GeocodeMentions(gazetteer, settings.geo_min_confidence),
        )
        show(await use_case.run(search_id))
        return 0
    finally:
        await engine.dispose()


async def _reprocess(
    search_id: UUID, settings: Settings, engine: AsyncEngine, ask: Callable[[str], str]
) -> int:
    try:
        llm = build_llm(settings)
    except MissingLLMKeyError as error:
        logger.error(f"{error} Pégala en .env y vuelve a intentar.")
        return 1
    try:
        store = PostgresArticleStore(engine)
        texts = await store.search_texts(search_id)
        estimate = estimated_usage(len(texts)).cost_usd(
            llm.price_input_per_million, llm.price_output_per_million
        )
        heading(logger, "Volver a pasar por la IA (todavía no se ha gastado nada)")
        logger.info(
            f"{len(texts)} notas con texto guardado · IA: {llm.provider} · {llm.llm.model} · "
            f"~{estimate:.4f} USD · 0 créditos de SearchApi"
        )
        if ask(f'Escribe "{CONFIRMATION}" para reprocesar: ').strip().lower() != CONFIRMATION:
            logger.warning("Cancelado: no se gastó nada.")
            return 1
        gazetteer = PostgresGazetteer(engine)
        report = await ReprocessSearch(
            searches=PostgresSearchStore(engine),
            store=store,
            gazetteer=gazetteer,
            geocoder=GeocodeMentions(gazetteer, settings.geo_min_confidence),
            llm=llm.llm,
            limits=PipelineLimits(
                settings.llm_max_articles_per_search,
                settings.llm_concurrency,
                llm.price_input_per_million,
                llm.price_output_per_million,
            ),
        ).run(search_id)
    finally:
        await llm.llm.aclose()
    show(report.relocations)
    logger.info(
        f"IA: {report.usage.tokens_in} tokens de entrada y {report.usage.tokens_out} de salida, "
        f"~{report.cost_usd:.4f} USD · fallas: {report.failed}"
    )
    return 0


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
