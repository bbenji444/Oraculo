"""Comando ``make reubicar``: vuelve a ubicar las notas de una búsqueda sin pagar a la IA.

Para qué: después de corregir el geolocalizador o el catálogo (alias
nuevos, reglas nuevas), ver el efecto en una búsqueda real sin volver a
consultar proveedores ni a la IA. Muestra, nota por nota, la ubicación
principal antes y después, y los conteos de dentro, fuera y sin ubicación.

Uso:
    ``make reubicar`` (la búsqueda más reciente) o
    ``make reubicar ARGS="--busqueda <id>"``.

No hace: no gasta créditos ni tokens.
"""

import argparse
import asyncio
import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.gazetteer_repository import PostgresGazetteer
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.relocate import RelocateSearch, Relocation
from app.core.config import Settings, get_settings
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
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, settings: Settings) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.

    Returns:
        Código de salida: 0 bien, 1 si no hay búsqueda.
    """
    engine = create_async_engine(settings.database_url())
    try:
        searches = PostgresSearchStore(engine)
        search_id = args.busqueda or await searches.last_search_id()
        if search_id is None:
            logger.error("No hay búsquedas todavía. Corre primero `make buscar`.")
            return 1
        gazetteer = PostgresGazetteer(engine)
        use_case = RelocateSearch(
            searches,
            PostgresArticleStore(engine),
            gazetteer,
            GeocodeMentions(gazetteer, settings.geo_min_confidence),
        )
        logger.info(f"Búsqueda {search_id}")
        show(await use_case.run(search_id))
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
