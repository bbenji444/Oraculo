"""Comando ``make comparar-fuentes``: cuánto aporta SearchApi que no traiga Google News RSS (F12.2).

Para qué: SearchApi y Google News RSS sacan las notas del mismo lugar
(Google Noticias), pero SearchApi cuesta créditos. Este comando hace **la
misma** consulta de un concepto en las dos fuentes, junta las notas
repetidas con la regla de siempre (``dedupe``) y dice cuántas trajo solo
cada una y cuántas las dos, con 5 ejemplos de lo que solo trajo SearchApi.
Con eso se decide si SearchApi queda encendido por defecto (ADR-0027).

Uso:
    ``make comparar-fuentes ARGS="--concepto 'Fiscalia General de la Republica' --dias 2"``

Antes de enviar muestra las dos consultas y los créditos (hasta 3, una
consulta de SearchApi con hasta 3 páginas) y pide escribir "si". Las
consultas quedan en ``provider_queries`` y cuentan para el tope mensual. No
pasa nada por la IA ni guarda notas.

No hace: no corre una búsqueda completa (eso es ``make buscar``).
"""

import argparse
import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.providers.factory import build_provider
from app.adapters.text.similarity import title_similarity
from app.application.audit import Actor
from app.application.clock import MEXICO_CITY
from app.cli.probar_proveedor import (
    NOT_CONFIGURED,
    build_plan,
    confirmed,
    execute,
    show_plan,
    window_from,
)
from app.core.config import Settings, get_settings
from app.domain.articles import RawArticle
from app.domain.budget import MonthlyCredits, month_start
from app.domain.dedupe import DedupedArticle, dedupe
from app.domain.queries import Provider
from app.geodata.consola import configure_cli_logging, heading

logger = logging.getLogger(__name__)

# Las dos fuentes que se comparan: la de pago y la gratuita de la misma
# fuente (Google Noticias).
COMPARED = (Provider.SEARCHAPI, Provider.GOOGLE_NEWS_RSS)
# CLAUDE.md §2.6: 5 ejemplos reales.
SAMPLE_SIZE = 5
TITLE_CHARS = 95


@dataclass(slots=True)
class Comparison:
    """Qué trajo cada fuente después de juntar las repetidas.

    Attributes:
        by_source: Notas que trajo cada fuente (con repetidas entre ellas).
        only_searchapi: Notas que solo trajo SearchApi.
        only_rss: Notas que solo trajo Google News RSS.
        both: Notas que trajeron las dos.
    """

    by_source: dict[str, int] = field(default_factory=dict)
    only_searchapi: list[DedupedArticle] = field(default_factory=list)
    only_rss: list[DedupedArticle] = field(default_factory=list)
    both: list[DedupedArticle] = field(default_factory=list)


def compare(articles: Sequence[RawArticle]) -> Comparison:
    """Junta las notas de las dos fuentes y las clasifica por quién las trajo.

    Args:
        articles: Notas de SearchApi y de Google News RSS.

    Returns:
        Conteos y listas de cada grupo.
    """
    result = Comparison()
    for provider in COMPARED:
        result.by_source[provider.value] = sum(1 for a in articles if a.provider is provider)
    for item in dedupe(articles, title_similarity):
        found = {s.provider for s in item.sightings}
        if found == {Provider.SEARCHAPI.value}:
            result.only_searchapi.append(item)
        elif found == {Provider.GOOGLE_NEWS_RSS.value}:
            result.only_rss.append(item)
        else:
            result.both.append(item)
    return result


def show(result: Comparison) -> None:
    """Muestra la comparación y los ejemplos.

    Args:
        result: Resultado de ``compare``.
    """
    heading(logger, "Comparación de fuentes")
    logger.info(
        f"SearchApi trajo {result.by_source[Provider.SEARCHAPI.value]} · "
        f"Google News RSS trajo {result.by_source[Provider.GOOGLE_NEWS_RSS.value]}"
    )
    logger.info(
        f"Notas distintas: solo SearchApi {len(result.only_searchapi)} · "
        f"solo RSS {len(result.only_rss)} · las dos {len(result.both)}"
    )
    with_snippet = sum(1 for d in result.only_searchapi if d.article.snippet)
    logger.info(f"De las que solo trajo SearchApi, {with_snippet} traen fragmento de la nota.")
    if result.only_searchapi:
        heading(logger, f"{min(SAMPLE_SIZE, len(result.only_searchapi))} que solo trajo SearchApi")
    for item in result.only_searchapi[:SAMPLE_SIZE]:
        a = item.article
        logger.info(
            f"{a.title[:TITLE_CHARS]}\n   {a.source_name or a.source_domain or '—'} · {a.url}"
        )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Compara SearchApi contra Google News RSS.")
    parser.add_argument("--concepto", required=True, help="nombre del concepto")
    parser.add_argument("--region", default="MEX", help="clave INEGI o ISO-A3 (MEX, 09, 14)")
    parser.add_argument("--dias", type=int, default=2)
    parser.add_argument("--desde", type=lambda s: datetime.fromisoformat(s).date())
    parser.add_argument("--hasta", type=lambda s: datetime.fromisoformat(s).date())
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, settings: Settings, ask: Callable[[str], str]) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.
        ask: Función para pedir confirmación.

    Returns:
        Código de salida: 0 bien, 1 cancelado, sin configurar o con error.
    """
    engine = create_async_engine(settings.database_url())
    try:
        providers = [build_provider(p, settings, engine) for p in COMPARED]
        missing = [p for p in providers if not p.is_configured()]
        if missing:
            for p in missing:
                logger.error(NOT_CONFIGURED[p.provider])
            return 1
        window = window_from(args)
        plans = [
            await build_plan(
                provider=p,
                concepts=PostgresConceptRepository(engine),
                regions=PostgresRegionRepository(engine),
                concept_name=args.concepto,
                region_code=args.region,
                window=window,
            )
            for p in providers
        ]
        for plan in plans:
            show_plan(plan)
        planned_credits = sum(plan.credits for plan in plans)
        log = PostgresProviderQueryLog(engine)
        used = await log.credits_used_since(
            Provider.SEARCHAPI.value, month_start(datetime.now(UTC), MEXICO_CITY)
        )
        limit = settings.searchapi_monthly_credit_limit
        logger.info(f"Hasta {planned_credits} crédito(s) · este mes van {used} de {limit}")
        if not MonthlyCredits(used=used, limit=limit).try_reserve(planned_credits):
            logger.error("Se alcanzaría el tope mensual de créditos: no se envió nada.")
            return 1
        if not confirmed(ask):
            logger.warning("Cancelado: no se envió nada.")
            return 1
        actor = Actor(settings.dev_user)
        responses = [
            await execute(provider=p, plan=plan, log=log, actor=actor)
            for p, plan in zip(providers, plans, strict=True)
        ]
        if any(r is None for r in responses):
            return 1
        show(compare([a for r in responses if r is not None for a in r.articles]))
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
    raise SystemExit(asyncio.run(run(args, get_settings(), input)))


if __name__ == "__main__":
    main()
