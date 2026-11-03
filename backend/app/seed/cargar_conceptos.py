"""Comando ``make seed``: carga los conceptos semilla y los temas de las subdivisiones.

Lee ``conceptos.json`` y crea **solo los que no existen**, comparando el
nombre sin mayúsculas ni acentos. Nunca modifica un concepto existente: si
alguien ya editó sus palabras clave, sus cambios se respetan. Correrlo dos
veces no hace nada la segunda vez.

Desde la Fase 12 (F12.6) el archivo trae solo el concepto de la FGR, con
su regla de relevancia ``fgr_federal`` (ADR-0030): los cinco conceptos de la
especificación se retiraron con ``make retirar-conceptos`` y una instalación
nueva (la VM de Proxmox) arranca ya enfocada en la FGR. La regla se pone solo
si el concepto todavía tiene la ``general``.

Desde el 02/11/2026 también lee ``temas.json``: un tema general por
subdivisión (menos «Otros»), para buscar «Homicidio» sin la FGR o para
combinarlo con ella («FGR + Homicidio»). El tema se llama y se pinta como su
subdivisión y queda ligado a ella (``concepts.category_id``). Si la
subdivisión ya tiene tema, no se toca: sus palabras se editan en pantalla.

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
from dataclasses import dataclass, replace
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
TOPICS_PATH = Path(__file__).with_name("temas.json")
# Color de un tema cuya subdivisión todavía no tiene color (el gris de «Otros»).
FALLBACK_TOPIC_COLOR = "#94A3B8"
# Firma de las altas en la bitácora: se distinguen de las de una persona.
SEED_ACTOR = Actor("semilla")


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Qué hizo la semilla.

    Attributes:
        created: Nombres de los conceptos creados.
        skipped: Nombres que ya existían y no se tocaron.
        missing: Subdivisiones de ``temas.json`` que no están en el catálogo
            (por ejemplo, si se renombraron antes de sembrar).
    """

    created: tuple[str, ...]
    skipped: tuple[str, ...]
    missing: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TopicSeed:
    """Un tema general de ``temas.json``.

    Attributes:
        category: Nombre de su subdivisión (se compara sin acentos).
        concept: El concepto; su nombre y color se toman de la subdivisión.
    """

    category: str
    concept: ConceptInput


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


def read_topics(path: Path = TOPICS_PATH) -> list[TopicSeed]:
    """Lee los temas generales de las subdivisiones.

    Args:
        path: Archivo JSON con un tema por subdivisión.

    Returns:
        Los temas, sin validar todavía.
    """
    items = json.loads(path.read_text(encoding="utf-8"))
    return [
        TopicSeed(
            item["category"],
            ConceptInput(
                name=item["category"],
                description=item["description"],
                keywords=tuple(item["keywords"]),
                exclude_terms=tuple(item["exclude_terms"]),
                color=FALLBACK_TOPIC_COLOR,
            ),
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


async def seed_topics(engine: AsyncEngine, topics: Sequence[TopicSeed]) -> SeedResult:
    """Crea el tema general de cada subdivisión que todavía no tenga uno.

    Args:
        engine: Conexión a la base.
        topics: Temas de ``temas.json``.

    Returns:
        Los creados, los que ya tenían tema (o cuyo nombre ya usa otro
        concepto) y las subdivisiones que no se encontraron.

    Raises:
        ConceptValidationError: Si algún tema del archivo no cumple las
            reglas (se detecta antes de crear ninguno).
    """
    for topic in topics:
        topic.concept.validated()
    repository = PostgresConceptRepository(engine)
    created: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    for topic in topics:
        async with engine.connect() as conn:
            category = (
                await conn.execute(
                    text("SELECT id, name, color FROM categories WHERE name_norm = :norm"),
                    {"norm": normalize_name(topic.category)},
                )
            ).first()
        if category is None:
            missing.append(topic.category)
            continue
        data = replace(
            topic.concept, name=category.name, color=category.color or FALLBACK_TOPIC_COLOR
        )
        already = await repository.for_category(category.id)
        if already is not None or await repository.name_taken(data.validated().name_norm, None):
            skipped.append(category.name)
            continue
        concept = await CreateConcept(repository).execute(data, SEED_ACTOR)
        # La alta pasa por el caso de uso (reglas y bitácora); el enlace con
        # la subdivisión es solo de la semilla, por eso va aparte.
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE concepts SET category_id = :category WHERE id = :id"),
                {"category": category.id, "id": concept.id},
            )
        created.append(category.name)
    return SeedResult(tuple(created), tuple(skipped), tuple(missing))


async def _run() -> tuple[SeedResult, SeedResult]:
    engine = create_async_engine(get_settings().database_url())
    try:
        result = await seed_concepts(engine, read_seed())
        await apply_rules(engine, read_rules())
        return result, await seed_topics(engine, read_topics())
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    argparse.ArgumentParser(description="Carga los conceptos semilla.").parse_args(argv)
    configure_cli_logging()
    heading(logger, f"Conceptos semilla ({SEED_PATH.name}) y temas ({TOPICS_PATH.name})")
    concepts, topics = asyncio.run(_run())
    for name in concepts.created:
        logger.info(f"Creado: {name}")
    for name in concepts.skipped:
        logger.info(f"Ya existía, no se tocó: {name}")
    logger.info(f"{len(concepts.created)} creados · {len(concepts.skipped)} ya existían")
    for name in topics.created:
        logger.info(f"Tema creado: {name}")
    for name in topics.skipped:
        logger.info(f"Ya tenía tema, no se tocó: {name}")
    for name in topics.missing:
        logger.warning(f"No existe la subdivisión «{name}»: su tema no se creó.")
    logger.info(
        f"Temas: {len(topics.created)} creados · {len(topics.skipped)} ya estaban · "
        f"{len(topics.missing)} sin subdivisión"
    )


if __name__ == "__main__":
    main()
