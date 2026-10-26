"""Comando ``make seed``: carga los conceptos semilla (especificación §7.1).

Lee ``conceptos.json`` y crea **solo los que no existen**, comparando el
nombre sin mayúsculas ni acentos. Nunca modifica un concepto existente: si
alguien ya editó sus palabras clave, sus cambios se respetan. Correrlo dos
veces no hace nada la segunda vez.

Desde la Fase 12 (F12.6) el archivo trae solo el concepto de la FGR, con
su regla de relevancia ``fgr_federal`` (ADR-0030): los cinco conceptos de la
especificación se retiraron con ``make retirar-conceptos`` y una instalación
nueva (la VM de Proxmox) arranca ya enfocada en la FGR. La regla se pone solo
si el concepto todavía tiene la ``general``.

Usa el mismo caso de uso que la API (``CreateConcept``), así que aplica las
mismas reglas y deja cada alta en la bitácora con el usuario ``semilla``.

Uso: ``python -m app.seed.cargar_conceptos``

No hace: no borra ni desactiva conceptos que no estén en el archivo.
"""

import argparse
import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.application.audit import Actor
from app.application.use_cases.concepts import ConceptInput, CreateConcept
from app.core.config import get_settings
from app.domain.authority import RelevanceRule
from app.domain.concept import ConceptDraft
from app.domain.names import normalize_name
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).with_name("conceptos.json")
# Firma de las altas en la bitácora: se distinguen de las de una persona.
SEED_ACTOR = Actor("semilla")


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Qué hizo la semilla.

    Attributes:
        created: Nombres de los conceptos creados.
        skipped: Nombres que ya existían y no se tocaron.
    """

    created: tuple[str, ...]
    skipped: tuple[str, ...]


def read_seed(path: Path = SEED_PATH) -> list[ConceptInput]:
    """Lee el archivo de conceptos semilla.

    Args:
        path: Archivo JSON con una lista de conceptos.

    Returns:
        Los conceptos, sin validar todavía.
    """
    items = json.loads(path.read_text(encoding="utf-8"))
    return [
        ConceptInput(
            name=item["name"],
            description=item["description"],
            keywords=tuple(item["keywords"]),
            exclude_terms=tuple(item["exclude_terms"]),
            color=item["color"],
        )
        for item in items
    ]


def read_rules(path: Path = SEED_PATH) -> dict[str, RelevanceRule]:
    """Regla de relevancia de cada concepto semilla que la pida.

    Args:
        path: Archivo JSON de la semilla.

    Returns:
        ``{nombre normalizado: regla}``; los que no traen ``relevance_rule``
        no aparecen (se quedan con la ``general``).
    """
    items = json.loads(path.read_text(encoding="utf-8"))
    return {
        normalize_name(item["name"]): RelevanceRule(item["relevance_rule"])
        for item in items
        if "relevance_rule" in item
    }


async def apply_rules(engine: AsyncEngine, rules: dict[str, RelevanceRule]) -> None:
    """Pone la regla de relevancia a los conceptos que todavía tienen la general.

    Args:
        engine: Conexión a la base.
        rules: Regla por nombre normalizado.
    """
    async with engine.begin() as conn:
        for name_norm, rule in rules.items():
            await conn.execute(
                text(
                    "UPDATE concepts SET relevance_rule = :rule WHERE name_norm = :norm "
                    "AND deleted_at IS NULL AND relevance_rule = 'general'"
                ),
                {"rule": rule.value, "norm": name_norm},
            )


async def seed_concepts(engine: AsyncEngine, concepts: Sequence[ConceptInput]) -> SeedResult:
    """Crea los conceptos que falten.

    Args:
        engine: Conexión a la base.
        concepts: Conceptos semilla.

    Returns:
        Los creados y los que ya existían.

    Raises:
        ConceptValidationError: Si algún concepto del archivo no cumple las
            reglas (se detecta antes de crear ninguno).
    """
    drafts: list[ConceptDraft] = [c.validated() for c in concepts]
    repository = PostgresConceptRepository(engine)
    created: list[str] = []
    skipped: list[str] = []
    for data, draft in zip(concepts, drafts, strict=True):
        if await repository.name_taken(draft.name_norm, None):
            skipped.append(draft.name)
            continue
        await CreateConcept(repository).execute(data, SEED_ACTOR)
        created.append(draft.name)
    return SeedResult(tuple(created), tuple(skipped))


async def _run() -> SeedResult:
    engine = create_async_engine(get_settings().database_url())
    try:
        result = await seed_concepts(engine, read_seed())
        await apply_rules(engine, read_rules())
        return result
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    argparse.ArgumentParser(description="Carga los conceptos semilla.").parse_args(argv)
    configure_cli_logging()
    heading(logger, f"Conceptos semilla ({SEED_PATH.name})")
    result = asyncio.run(_run())
    for name in result.created:
        logger.info(f"Creado: {name}")
    for name in result.skipped:
        logger.info(f"Ya existía, no se tocó: {name}")
    logger.info(f"{len(result.created)} creados · {len(result.skipped)} ya existían")


if __name__ == "__main__":
    main()
