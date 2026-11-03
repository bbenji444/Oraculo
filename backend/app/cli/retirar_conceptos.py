"""Comando ``make retirar-conceptos``: deja vigente solo el concepto de la FGR (F12.6).

Benji pidió enfocar el monitor 100 % en la FGR y quitar los conceptos de
antes. Se hace con **borrado lógico** (plan F12 §4.8): los conceptos
retirados dejan de verse en Explorar y en Conceptos, pero las búsquedas,
los casos y los reportes que los usaron siguen intactos. Cada retiro queda
en la bitácora con el usuario ``f12.6``.

Además, si el concepto FGR no tiene descripción, le pone la del plan (§4.5):
la IA la lee al juzgar la relevancia de cada nota nueva.

Uso:
    ``make retirar-conceptos``: muestra qué se queda y qué se retiraría, sin
    cambiar nada.
    ``make retirar-conceptos ARGS=--aplicar``: lo hace (pide "si"; antes
    ``make db-dump``).

No hace: no borra nada en seco ni toca las notas.
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.application.audit import Actor
from app.application.use_cases.concepts import RetireConcepts, UpdateConcept
from app.cli.buscar import CONFIRMATION
from app.core.config import Settings, get_settings
from app.domain.concept import Concept, ConceptChanges
from app.domain.names import normalize_name
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

# Nombre del concepto que se queda (Benji lo creó así el 24/10/2026).
FGR_CONCEPT = "Fiscalia General de la Republica"
# Lo que la IA debe entender por el concepto (plan F12 §4.5, ADR-0030).
FGR_DESCRIPTION = (
    "Noticias donde actúa la Fiscalía General de la República (FGR) federal: "
    "detenciones, cateos, aseguramientos, órdenes de aprehensión, carpetas de "
    "investigación, acusaciones, sentencias, extradiciones y nombramientos. "
    "También el Ministerio Público Federal, la AIC y las fiscalías especializadas "
    "federales. No cuentan las fiscalías estatales ni las notas que solo nombran "
    "a la FGR de pasada."
)
ACTOR = Actor("f12.6")
REASON = "F12.6: el monitor se enfoca en la FGR (plan F12 §4.8)"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Deja vigente solo el concepto de la FGR.")
    parser.add_argument("--aplicar", action="store_true", help='retirar los demás (pide "si")')
    return parser.parse_args(argv)


def _names(concepts: Sequence[Concept]) -> str:
    return ", ".join(c.data.name for c in concepts) or "ninguno"


async def run(
    args: argparse.Namespace, settings: Settings, ask: Callable[[str], str] = input
) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.
        ask: Función para pedir confirmación.

    Returns:
        0 bien; 1 si se canceló o no existe el concepto FGR.
    """
    engine = create_async_engine(settings.database_url())
    try:
        repository = PostgresConceptRepository(engine)
        retire = RetireConcepts(repository)
        kept, retired = await retire.plan([FGR_CONCEPT])
        heading(logger, "Conceptos (todavía no se ha cambiado nada)")
        logger.info(f"Se queda: {_names(kept)}")
        logger.info(f"Se retirarían ({len(retired)}): {_names(retired)}")
        # Los temas de las subdivisiones también se quedan: la FGR se busca por nombre.
        fgr = next((c for c in kept if c.data.name_norm == normalize_name(FGR_CONCEPT)), None)
        if fgr is None:
            logger.error(f"No existe el concepto «{FGR_CONCEPT}»: créalo antes de retirar.")
            return 1
        if not args.aplicar:
            logger.info("Para hacerlo: make retirar-conceptos ARGS=--aplicar")
            return 0
        if ask(f'Escribe "{CONFIRMATION}" para retirarlos: ').strip().lower() != CONFIRMATION:
            logger.warning("Cancelado: no se cambió nada.")
            return 1
        done = await retire.execute([FGR_CONCEPT], ACTOR, REASON)
        logger.info(f"Retirados {len(done)} conceptos (borrado lógico, en la bitácora).")
        if not fgr.data.description:
            await UpdateConcept(repository).execute(
                fgr.id, ConceptChanges(description=FGR_DESCRIPTION), ACTOR
            )
            logger.info("El concepto FGR ya tiene descripción (la lee la IA).")
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
