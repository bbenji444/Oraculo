"""Una corrida automática de punta a punta (F12.8, ADR-0031, ADR-0046).

La lanza el reloj de Celery cuando llega una hora de algún envío programado
(«Mis envíos», ADR-0046): los envíos que piden lo mismo a la misma hora
comparten una corrida. ``make corrida-fgr`` corre a mano la del monitor FGR.
Hace lo mismo que alguien en Explorar, sin pantalla:

1. arma la petición (``PrepareAutomaticRun``): los temas y la región del
   envío, solo las horas desde su corrida anterior, Google News RSS y el
   índice local (0 créditos);
2. la crea con las mismas reglas que una manual (``StartSearch``: tope de
   consultas, llave de la IA, tope de créditos) y la marca como automática;
3. la corre aquí mismo con el pipeline de siempre (``run_search_job``): extrae,
   resume, ubica, clasifica por categoría y quién actúa, y agrupa historias;
4. arma su reporte (resumen ejecutivo, mapa y conteos) y guarda el PDF en
   ``REPORTS_DIR``, con su ruta en ``reports.pdf_path``. El reporte separa
   lo nuevo de lo que ya traía la corrida anterior (ADR-0034).

Todo queda en PostgreSQL: la búsqueda, sus notas, la bitácora y el reporte.

5. si los envíos están prendidos (``DELIVERIES_ENABLED``), manda el reporte
   a los correos de los envíos que la pidieron (ADR-0039, ADR-0046).

``check_due_runs`` es lo que hace el reloj cada minuto: ¿qué corridas tocan?

No hace: no guarda el horario (eso es la API) ni programa el reloj (``celery_app``).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.adapters.llm.factory import MissingLLMKeyError, build_summarizer, llm_info
from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.adapters.persistence.delivery_schedules_repository import (
    PostgresDeliveryScheduleStore,
)
from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.persistence.reports_repository import PostgresReportStore
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.adapters.reports.render import ReportRenderer
from app.adapters.reports.static_map import PostgisStaticMap
from app.application.audit import Actor
from app.application.clock import MEXICO_CITY
from app.application.use_cases.automatic_run import AutomaticProfile, PrepareAutomaticRun
from app.application.use_cases.delivery_schedules import PendingRuns
from app.application.use_cases.plan_search import PlanSearch, SearchRequest
from app.application.use_cases.reports import BuildReport, LLMPrices, ReportFormat
from app.application.use_cases.run_search import SearchReport
from app.application.use_cases.start_search import StartSearch
from app.core.config import Settings
from app.domain.delivery_schedules import DueRun, topic_key
from app.domain.schedule import RunSchedule, RunWindow, parse_run_hours
from app.domain.sources import parse_sources
from app.worker.delivery_jobs import deliver_run
from app.worker.search_jobs import build_providers, run_search_job

logger = logging.getLogger(__name__)

# El reloj revisa cada minuto; una corrida se lanza si su hora llegó hace menos
# de 10 minutos. Cubre una revisión atrasada o un reinicio breve del reloj sin
# lanzar corridas viejas al arrancar después de horas apagado.
DUE_GRACE = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class AutomaticRunSummary:
    """Cómo terminó una corrida automática.

    Attributes:
        search_id: La búsqueda que creó.
        scheduled_for: La corrida programada a la que pertenece (CDMX).
        report: Resultado del pipeline (estado, notas, créditos, costo).
        pdf_path: Dónde quedó el PDF, o ``None`` si no se pudo armar.
    """

    search_id: UUID
    scheduled_for: datetime
    report: SearchReport
    pdf_path: Path | None


class _RunsHere:
    """«Cola» que no encola: la corrida automática ya está en el worker y corre aquí."""

    def enqueue(self, search_id: UUID) -> None:
        """No hace nada: ``run_automatic_job`` corre la búsqueda en seguida.

        Args:
            search_id: Búsqueda creada.
        """


def profile_from(settings: Settings) -> AutomaticProfile:
    """El perfil fijo de las corridas, desde la configuración.

    Args:
        settings: Configuración (``AUTOMATIC_*``).

    Returns:
        El perfil.
    """
    return AutomaticProfile(
        concept=settings.automatic_concept,
        region_code=settings.automatic_region_code,
        sources=parse_sources(settings.automatic_sources),
        user_id=settings.automatic_user,
        margin_minutes=settings.automatic_window_margin_minutes,
    )


def default_schedule(settings: Settings) -> RunSchedule:
    """El horario inicial, mientras el administrador no guarde uno (``AUTOMATIC_RUN_HOURS``).

    Args:
        settings: Configuración.

    Returns:
        El horario con esas horas, todos los días.
    """
    return RunSchedule.from_hours(parse_run_hours(settings.automatic_run_hours))


async def check_due_runs(settings: Settings, now: datetime | None = None) -> list[DueRun]:
    """Lo que hace el reloj cada minuto: ¿qué corridas de los envíos programados tocan?

    Args:
        settings: Configuración.
        now: Este momento (por defecto, ahora).

    Returns:
        Las corridas, ya agrupadas y apartadas para que nadie más las lance.
    """
    engine = create_async_engine(settings.database_url())
    try:
        pending = PendingRuns(
            PostgresDeliveryScheduleStore(engine),
            DUE_GRACE,
            timedelta(minutes=settings.automatic_window_margin_minutes),
        )
        return await pending.execute(now or datetime.now(UTC))
    finally:
        await engine.dispose()


def run_to_payload(run: DueRun) -> dict[str, Any]:
    """Una corrida apartada, en datos simples para la cola de Celery (JSON).

    Args:
        run: La corrida.

    Returns:
        Lo que recibe ``run_from_payload``.
    """
    return {
        "topic": run.topic,
        "concept_ids": list(run.concept_ids),
        "region_id": run.region_id,
        "start": run.window.start.isoformat(),
        "end": run.window.end.isoformat(),
        "schedule_ids": list(run.schedule_ids),
    }


def run_from_payload(payload: dict[str, Any]) -> DueRun:
    """Lo contrario de ``run_to_payload``.

    Args:
        payload: Lo que viajó por la cola.

    Returns:
        La corrida.
    """
    return DueRun(
        topic=str(payload["topic"]),
        concept_ids=tuple(int(c) for c in payload["concept_ids"]),
        region_id=int(payload["region_id"]),
        window=RunWindow(
            datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end"])
        ),
        schedule_ids=tuple(int(s) for s in payload["schedule_ids"]),
    )


def report_file_name(scheduled_for: datetime, search_id: UUID | None = None) -> str:
    """Nombre del PDF de una corrida: ``fgr_2026-10-26_0700.pdf``.

    Las corridas de los envíos programados llevan además el inicio del id de
    su búsqueda, porque a la misma hora puede haber varias de temas distintos.

    Args:
        scheduled_for: Hora programada (CDMX).
        search_id: La búsqueda de la corrida, si es de un envío programado.

    Returns:
        El nombre, ordenable por fecha en cualquier explorador de archivos.

    Example:
        >>> report_file_name(datetime(2026, 11, 11, 16, 0), UUID(int=0xABCDEF12 << 96))
        'corrida_2026-11-11_1600_abcdef12.pdf'
    """
    if search_id is None:
        return f"fgr_{scheduled_for:%Y-%m-%d_%H%M}.pdf"
    return f"corrida_{scheduled_for:%Y-%m-%d_%H%M}_{search_id.hex[:8]}.pdf"


def automatic_settings(settings: Settings) -> Settings:
    """La configuración de una corrida automática: su propio tope de notas para la IA.

    Las corridas cubren todo México y dos días, y traen más notas que una
    búsqueda manual; con el tope general (150) algunas esperaban a la corrida
    siguiente (27/10/2026). El resto de la configuración es la misma.

    Args:
        settings: Configuración general.

    Returns:
        Una copia con ``llm_max_articles_per_search`` = ``automatic_llm_max_articles``.
    """
    return settings.model_copy(
        update={"llm_max_articles_per_search": settings.automatic_llm_max_articles}
    )


async def run_scheduled_job(settings: Settings, run: DueRun) -> AutomaticRunSummary:
    """Corre la corrida de uno o varios envíos programados y les manda el reporte.

    Args:
        settings: Configuración.
        run: La corrida que apartó el reloj (``check_due_runs``).

    Returns:
        La búsqueda creada, su resultado y la ruta del PDF.

    Raises:
        LLMNotConfiguredError, ServiceUnavailableError: Ver ``StartSearch``.
    """
    settings = automatic_settings(settings)
    slot = run.slot.astimezone(MEXICO_CITY)
    engine = create_async_engine(settings.database_url())
    try:
        concepts = PostgresConceptRepository(engine)
        regions = PostgresRegionRepository(engine)
        request = PrepareAutomaticRun(concepts, regions, profile_from(settings)).request_for(run)
        search_id = await _start(settings, engine, request)
        await PostgresDeliveryScheduleStore(engine).set_topic(search_id, run.topic)
    finally:
        await engine.dispose()
    logger.info(
        "Corrida automática creada",
        extra={
            "search_id": str(search_id),
            "corrida": slot.isoformat(),
            "tema": run.topic,
            "envios": list(run.schedule_ids),
        },
    )
    report = await run_search_job(settings, search_id)
    pdf_path = await _save_report(settings, search_id, report_file_name(slot, search_id))
    await deliver_run(settings, search_id, slot, run.schedule_ids)
    return AutomaticRunSummary(search_id, slot, report, pdf_path)


async def run_automatic_job(
    settings: Settings, now: datetime | None = None, slot: datetime | None = None
) -> AutomaticRunSummary:
    """Corre a mano la corrida del monitor FGR (``make corrida-fgr``).

    Usa el perfil fijo de la configuración (FGR, todo México) y el horario
    ``AUTOMATIC_RUN_HOURS`` para saber qué periodo cubre. Guarda la búsqueda y
    su PDF, pero no manda correos: eso lo hacen los envíos programados.

    Args:
        settings: Configuración.
        now: Momento de la corrida (por defecto, ahora). Define a qué hora del
            horario pertenece.
        slot: Hora programada, si se quiere una en particular.

    Returns:
        La búsqueda creada, su resultado y la ruta del PDF.

    Raises:
        AutomaticRunConfigError: Si falta el concepto o la región del perfil.
        LLMNotConfiguredError, ServiceUnavailableError: Ver ``StartSearch``.
    """
    settings = automatic_settings(settings)
    local_now = (now or datetime.now(UTC)).astimezone(MEXICO_CITY)
    schedule = default_schedule(settings)
    slot = (slot or schedule.slot_at_or_before(local_now)).astimezone(MEXICO_CITY)
    engine = create_async_engine(settings.database_url())
    try:
        concepts = PostgresConceptRepository(engine)
        regions = PostgresRegionRepository(engine)
        prepare = PrepareAutomaticRun(concepts, regions, profile_from(settings))
        # Solo desde la corrida programada anterior a esta.
        request = await prepare.request(slot, schedule)
        search_id = await _start(settings, engine, request)
        await PostgresDeliveryScheduleStore(engine).set_topic(
            search_id, topic_key(request.concept_ids, request.region_id)
        )
    finally:
        await engine.dispose()
    logger.info(
        "Corrida automática creada",
        extra={"search_id": str(search_id), "corrida": slot.isoformat()},
    )
    report = await run_search_job(settings, search_id)
    pdf_path = await _save_report(settings, search_id, report_file_name(slot))
    return AutomaticRunSummary(search_id, slot, report, pdf_path)


async def _start(settings: Settings, engine: AsyncEngine, request: SearchRequest) -> UUID:
    concepts = PostgresConceptRepository(engine)
    regions = PostgresRegionRepository(engine)
    profile = profile_from(settings)
    planner = PlanSearch(
        concepts=concepts,
        regions=regions,
        providers=build_providers(settings, engine),
        log=PostgresProviderQueryLog(engine),
        llm=llm_info(settings),
        llm_max_articles=settings.llm_max_articles_per_search,
        credits_limit=settings.searchapi_monthly_credit_limit,
        default_sources=profile.sources,
    )
    started = await StartSearch(
        planner, PostgresSearchStore(engine), _RunsHere(), settings.max_queries_per_search
    ).execute(request)
    return started.search_id


async def _save_report(settings: Settings, search_id: UUID, file_name: str) -> Path | None:
    """Arma el reporte de la corrida y guarda su PDF; si falla, la corrida sigue valiendo."""
    engine = create_async_engine(settings.database_url())
    try:
        store = PostgresReportStore(engine)
        data = await _builder(settings, engine, store).execute(
            search_id, ReportFormat.PDF, Actor(settings.automatic_user)
        )
        # WeasyPrint es lento y síncrono (~1 s por 50 notas): en otro hilo.
        pdf = await asyncio.to_thread(ReportRenderer().pdf, data)
        path = settings.reports_dir / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf)
        await store.set_pdf_path(search_id, str(path))
        return path
    except Exception:
        # El reporte se puede volver a pedir desde Explorar; la búsqueda y sus
        # notas ya quedaron guardadas.
        logger.exception(
            "No se pudo armar el PDF de la corrida", extra={"search_id": str(search_id)}
        )
        return None
    finally:
        await engine.dispose()


def _builder(settings: Settings, engine: AsyncEngine, store: PostgresReportStore) -> BuildReport:
    try:
        summarizer = build_summarizer(settings)
    except MissingLLMKeyError:
        # Sin llave sale igual, con un aviso en lugar del resumen (ADR-0018).
        summarizer = None
    return BuildReport(
        searches=PostgresSearchStore(engine),
        articles=PostgresArticleStore(engine),
        regions=PostgresRegionRepository(engine),
        store=store,
        static_map=PostgisStaticMap(engine),
        summarizer=summarizer.summarizer if summarizer else None,
        prices=(
            LLMPrices(
                summarizer.provider,
                summarizer.price_input_per_million,
                summarizer.price_output_per_million,
            )
            if summarizer
            else None
        ),
        clock=lambda: datetime.now(UTC),
        previous_runs=PostgresSearchStore(engine),
    )
