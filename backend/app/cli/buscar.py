"""Comando ``make buscar``: una búsqueda real de punta a punta (§9, criterio de F4).

Pasos:

1. Arma las consultas igual que lo hará la API en F5: los conceptos
   guardados, la región (clave INEGI o ISO-A3) y el rango de fechas.
2. Muestra lo que costaría **antes de gastar**: las consultas y sus
   créditos de SearchApi (con lo ya gastado en el mes y su tope), y el
   costo máximo de la IA (``LLM_MAX_ARTICLES_PER_SEARCH`` notas a la tarifa
   del modelo elegido, ADR-0015). Luego **pide escribir "si"**.
3. Crea la búsqueda y la manda al worker de Celery (o la corre aquí mismo
   con ``--aqui``, sin worker). Mientras avanza, muestra cada etapa.
4. Al terminar muestra el resumen (estado, notas, créditos, costo) y
   **5 notas** con su resumen, concepto, lugar, precisión y confianza, para
   revisarlas a mano.

Uso:
    ``make buscar ARGS="--concepto Extorsión --region 14 --dias 7"``

No hace: no gasta nada si la respuesta no es "si".
"""

import argparse
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.adapters.llm.factory import MissingLLMKeyError, build_llm
from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.persistence.search_repository import (
    PostgresArticleStore,
    PostgresSearchStore,
    ResultPreview,
    SearchSnapshot,
)
from app.application.clock import MEXICO_CITY
from app.application.ports.search_store import NewSearch, SearchConcept
from app.application.use_cases.run_search import plan_queries
from app.cli.probar_proveedor import find_concept, window_from
from app.core.config import Settings, get_settings
from app.domain.budget import month_start
from app.domain.enrichment import estimated_usage
from app.domain.queries import PlannedQuery, Provider, place_for
from app.domain.search import SearchStatus, Stage
from app.geodata.consola import configure_cli_logging, heading
from app.worker.celery_app import celery_app
from app.worker.search_jobs import build_providers, run_search_job
from app.worker.tasks import SEARCH_TASK

logger = logging.getLogger(__name__)

# Respuesta que confirma el gasto: hay que escribirla completa.
CONFIRMATION = "si"
# Ejemplos que se muestran (CLAUDE.md §2.6: 5 ejemplos reales).
EXAMPLES = 5
# Cada cuánto se pregunta a la base cómo va la búsqueda que corre en el worker.
POLL_SECONDS = 2.0
# Cuánto se espera al worker antes de rendirse: 150 notas con extracción de
# hasta 15 s y la IA tardan unos minutos; 20 minutos sobra.
WAIT_LIMIT_SECONDS = 1200.0
SUMMARY_CHARS = 280
_FINISHED = {SearchStatus.COMPLETED, SearchStatus.PARTIAL, SearchStatus.FAILED}
STAGE_LABELS = {
    Stage.PLAN.value: "Planeando consultas",
    Stage.QUERY.value: "Consultando proveedores",
    Stage.DEDUPE.value: "Quitando duplicados",
    Stage.EXTRACT.value: "Leyendo el texto de las notas",
    Stage.ENRICH.value: "Resumiendo y clasificando con la IA",
    Stage.GEOCODE.value: "Ubicando en el catálogo INEGI",
    Stage.FILTER.value: "Revisando qué cae en la región",
    Stage.CLOSE.value: "Cerrando la búsqueda",
}
PRECISION_LABELS = {
    "country": "país",
    "state": "estado",
    "municipality": "municipio",
    "locality": "localidad",
    "unknown": "sin ubicar",
}


@dataclass(frozen=True, slots=True)
class Prepared:
    """Búsqueda lista para mostrar y, si se confirma, crear.

    Attributes:
        search: Datos para crear la fila de ``searches``.
        breadcrumb: Región elegida ("México › Jalisco").
        queries: Consultas que se enviarían.
        credits: Créditos de SearchApi estimados.
        credits_month: Créditos ya gastados este mes.
        credits_limit: Tope mensual (``SEARCHAPI_MONTHLY_CREDIT_LIMIT``).
        llm_label: IA y modelo ("openai · gpt-6-luna").
        llm_max_articles: Tope de notas para la IA.
        llm_max_cost_usd: Costo estimado si se enriquece el tope completo.
    """

    search: NewSearch
    breadcrumb: str
    queries: tuple[PlannedQuery, ...]
    credits: int
    credits_month: int
    credits_limit: int
    llm_label: str
    llm_max_articles: int
    llm_max_cost_usd: float

    @property
    def over_limit(self) -> bool:
        """``True`` si las consultas pasarían el tope mensual de créditos."""
        return self.credits_month + self.credits > self.credits_limit


async def prepare(args: argparse.Namespace, settings: Settings, engine: AsyncEngine) -> Prepared:
    """Arma la búsqueda y su costo sin gastar nada.

    Args:
        args: Opciones del comando.
        settings: Configuración.
        engine: Conexión a la base.

    Returns:
        Lo que se mostraría.

    Raises:
        SystemExit: Si un concepto o la región no existen.
        MissingLLMKeyError: Si falta la llave de la IA elegida.
    """
    llm = build_llm(settings)
    llm_label = f"{llm.provider} · {llm.llm.model}"
    await llm.llm.aclose()
    concepts_repo = PostgresConceptRepository(engine)
    concepts = [await find_concept(concepts_repo, name) for name in args.concepto]
    regions = PostgresRegionRepository(engine)
    region = await regions.get_by_code(args.region)
    facts = await regions.place_facts(region.id) if region else None
    if region is None or facts is None:
        raise SystemExit(f"No existe una región con clave {args.region}.")
    ancestors = await regions.ancestors(region.id)
    window = window_from(args)
    snapshots = tuple(
        SearchConcept(c.id, c.data.name, c.data.description, c.data.keywords, c.data.exclude_terms)
        for c in concepts
    )
    providers = build_providers(settings, engine)
    available = [p for p, adapter in providers.items() if adapter.is_configured()]
    queries = tuple(plan_queries(snapshots, place_for(facts), window, available))
    estimated = sum(providers[q.provider].estimate_cost(q) for q in queries)
    used = await PostgresProviderQueryLog(engine).credits_used_since(
        Provider.SEARCHAPI.value, month_start(datetime.now(UTC), MEXICO_CITY)
    )
    max_articles = settings.llm_max_articles_per_search
    return Prepared(
        search=NewSearch(
            user_id=settings.dev_user,
            region_id=region.id,
            date_from=window.date_from,
            date_to=window.date_to,
            concepts=snapshots,
            queries_planned=len(queries),
            credits_estimated=estimated,
        ),
        breadcrumb=" › ".join([*(a.name for a in ancestors), region.name]),
        queries=queries,
        credits=estimated,
        credits_month=used,
        credits_limit=settings.searchapi_monthly_credit_limit,
        llm_label=llm_label,
        llm_max_articles=max_articles,
        llm_max_cost_usd=estimated_usage(max_articles).cost_usd(
            llm.price_input_per_million, llm.price_output_per_million
        ),
    )


def show_prepared(prepared: Prepared) -> None:
    """Muestra lo que se haría y cuánto costaría.

    Args:
        prepared: Búsqueda armada.
    """
    search = prepared.search
    heading(logger, "Búsqueda (todavía no se ha gastado nada)")
    logger.info(f"Conceptos: {', '.join(c.name for c in search.concepts)}")
    logger.info(f"Región: {prepared.breadcrumb}")
    logger.info(
        f"Rango: {search.date_from.strftime('%d/%m/%Y')} a {search.date_to.strftime('%d/%m/%Y')}"
    )
    for query in prepared.queries:
        logger.info(f"  · {query.provider.value}: {query.text}")
    logger.info(
        f"Créditos de SearchApi: {prepared.credits} "
        f"(este mes van {prepared.credits_month} de {prepared.credits_limit})"
    )
    logger.info(
        f"IA: {prepared.llm_label}, hasta {prepared.llm_max_articles} notas, "
        f"~{prepared.llm_max_cost_usd:.4f} USD como máximo (las ya procesadas no se pagan)"
    )


def describe_progress(progress: Mapping[str, object]) -> str:
    """Una línea con la etapa y lo que va contado.

    Args:
        progress: ``searches.progress``.

    Returns:
        Texto para la pantalla.
    """
    stage = str(progress.get("stage", ""))
    label = STAGE_LABELS.get(stage, stage)
    counts = {
        "articles": "notas",
        "reused": "ya procesadas",
        "enriched": "resumidas",
        "fallback": "sin texto completo",
    }
    parts = [f"{progress[k]} {name}" for k, name in counts.items() if k in progress]
    return f"{label}" + (f" ({', '.join(parts)})" if parts else "")


class SnapshotReader(Protocol):
    """Lo único que ``wait_for`` necesita del repositorio de búsquedas."""

    async def snapshot(self, search_id: UUID) -> SearchSnapshot | None:
        """Ver ``PostgresSearchStore.snapshot``."""
        ...


async def wait_for(
    store: SnapshotReader,
    search_id: UUID,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    limit_seconds: float = WAIT_LIMIT_SECONDS,
) -> SearchSnapshot | None:
    """Espera a que el worker termine, mostrando cada cambio de etapa.

    Args:
        store: Búsquedas.
        search_id: Id.
        sleep: Pausa entre consultas (las pruebas la reemplazan).
        limit_seconds: Cuánto esperar como máximo.

    Returns:
        Cómo terminó, o ``None`` si se acabó el tiempo.
    """
    started = time.monotonic()
    last = ""
    while time.monotonic() - started < limit_seconds:
        snapshot = await store.snapshot(search_id)
        if snapshot is not None:
            line = describe_progress(snapshot.progress)
            if snapshot.progress and line != last:
                logger.info(f"… {line}")
                last = line
            if snapshot.status in _FINISHED:
                return snapshot
        await sleep(POLL_SECONDS)
    return None


def show_result(snapshot: SearchSnapshot, previews: Sequence[ResultPreview]) -> None:
    """Muestra el resumen y los ejemplos.

    Args:
        snapshot: Cómo terminó.
        previews: Primeras notas.
    """
    p = snapshot.progress
    heading(logger, f"Búsqueda {snapshot.status.value}")
    logger.info(
        f"Notas: {p.get('articles', 0)} · ya procesadas: {p.get('reused', 0)} · "
        f"resumidas ahora: {p.get('enriched', 0)} · sin enriquecer por tope: "
        f"{p.get('skipped_by_cap', 0)} · solo título y fragmento: {p.get('fallback', 0)}"
    )
    logger.info(
        f"En la región: {p.get('in_region', 0)} · fuera: {p.get('out_of_region', 0)} · "
        f"sin ubicación: {p.get('unlocated', 0)}"
    )
    logger.info(
        f"Créditos: {snapshot.credits_used} · IA: {snapshot.llm_usage.tokens_in} tokens de "
        f"entrada y {snapshot.llm_usage.tokens_out} de salida, ~{snapshot.llm_cost_usd:.4f} USD"
    )
    if snapshot.error_summary:
        logger.warning(f"Avisos: {snapshot.error_summary}")
    heading(logger, f"{min(EXAMPLES, len(previews))} ejemplos para revisar a mano")
    for n, item in enumerate(previews[:EXAMPLES], start=1):
        when = (
            item.published_at.astimezone(MEXICO_CITY).strftime("%d/%m/%Y")
            if item.published_at
            else "sin fecha"
        )
        place = (
            f"{item.place} ({PRECISION_LABELS.get(item.precision or '', item.precision)}, "
            f"confianza {item.confidence:.2f})"
            if item.place and item.confidence is not None
            else "Sin ubicación"
        )
        region = {True: "dentro de la región", False: "FUERA de la región", None: "—"}
        summary = (item.summary or "(sin resumen)")[:SUMMARY_CHARS]
        logger.info(
            f"{n}. [{when}] {item.source or '—'} — {item.title}\n"
            f"   Lugar: {place} · {region[item.in_region]}\n"
            f"   Conceptos: {', '.join(item.concepts) or 'ninguno relevante'}"
            f" · texto: {item.extraction_status}\n"
            f"   Resumen: {summary}\n"
            f"   {item.url}"
        )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Lee las opciones del comando.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).

    Returns:
        Las opciones.
    """
    parser = argparse.ArgumentParser(description="Corre una búsqueda real de punta a punta.")
    parser.add_argument(
        "--concepto", action="append", required=True, help="se puede repetir para varios"
    )
    parser.add_argument("--region", required=True, help="clave INEGI o ISO-A3 (09, 14, MEX)")
    parser.add_argument("--dias", type=int, default=7)
    parser.add_argument("--desde", type=date.fromisoformat, help="rango fijo: AAAA-MM-DD")
    parser.add_argument("--hasta", type=date.fromisoformat, help="rango fijo: AAAA-MM-DD")
    parser.add_argument(
        "--aqui", action="store_true", help="correrla en este proceso, sin el worker"
    )
    return parser.parse_args(argv)


def _enqueue(search_id: UUID) -> None:
    celery_app.send_task(SEARCH_TASK, args=[str(search_id)])


async def run(  # noqa: PLR0913 — dependencias que las pruebas reemplazan, todo por nombre (*)
    args: argparse.Namespace,
    settings: Settings,
    ask: Callable[[str], str],
    *,
    enqueue: Callable[[UUID], None] = _enqueue,
    run_here: Callable[[Settings, UUID], Awaitable[object]] | None = None,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> int:
    """Flujo completo del comando.

    Args:
        args: Opciones.
        settings: Configuración.
        ask: Función para pedir confirmación.
        enqueue: Manda la búsqueda al worker.
        run_here: Corre la búsqueda en este proceso (``--aqui``).
        sleep: Pausa entre consultas de avance.

    Returns:
        Código de salida: 0 bien, 1 cancelado o con error.
    """
    engine = create_async_engine(settings.database_url())
    try:
        try:
            prepared = await prepare(args, settings, engine)
        except MissingLLMKeyError as error:
            logger.error(f"{error} Pégala en .env y vuelve a intentar.")
            return 1
        show_prepared(prepared)
        if not prepared.queries:
            logger.error("No hay proveedores disponibles: no se envió nada.")
            return 1
        if prepared.over_limit:
            logger.error("Se pasaría el tope mensual de créditos: no se envió nada.")
            return 1
        answer = ask(f'Escribe "{CONFIRMATION}" para correr la búsqueda: ')
        if answer.strip().lower() != CONFIRMATION:
            logger.warning("Cancelado: no se gastó nada.")
            return 1
        store = PostgresSearchStore(engine)
        search_id = await store.create(prepared.search)
        logger.info(f"Búsqueda {search_id} creada.")
        if args.aqui:
            await (run_here or _run_here)(settings, search_id)
        else:
            enqueue(search_id)
            logger.info("Enviada al worker; esperando…")
        snapshot = await wait_for(store, search_id, sleep)
        if snapshot is None:
            logger.error(
                "El worker no terminó a tiempo. ¿Está corriendo? Revisa `make status` o usa --aqui."
            )
            return 1
        show_result(snapshot, await PostgresArticleStore(engine).preview(search_id, EXAMPLES))
        return 0 if snapshot.status is not SearchStatus.FAILED else 1
    finally:
        await engine.dispose()


async def _run_here(settings: Settings, search_id: UUID) -> object:
    def show(_id: UUID, progress: Mapping[str, object]) -> None:
        logger.info(f"… {describe_progress(progress)}")

    return await run_search_job(settings, search_id, show)


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
