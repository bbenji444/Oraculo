"""Una corrida automática del monitor FGR de punta a punta (F12.8, ADR-0031).

La lanza el reloj de Celery a las 07:00, 15:00 y 23:00 (CDMX), o una persona
con ``make corrida-fgr``. Hace lo mismo que alguien en Explorar, sin pantalla:

1. arma la petición (``PrepareAutomaticRun``): FGR, todo México, solo las
   horas desde la corrida anterior, Google News RSS y el índice local (0 créditos);
2. la crea con las mismas reglas que una manual (``StartSearch``: tope de
   consultas, llave de la IA, tope de créditos) y la marca como automática;
3. la corre aquí mismo con el pipeline de siempre (``run_search_job``): extrae,
   resume, ubica, clasifica por categoría y quién actúa, y agrupa historias;
4. arma su reporte (resumen ejecutivo, mapa y conteos) y guarda el PDF en
   ``REPORTS_DIR``, con su ruta en ``reports.pdf_path``. El reporte separa
   lo nuevo de lo que ya traía la corrida anterior (ADR-0034).

Todo queda en PostgreSQL: la búsqueda, sus notas, la bitácora y el reporte.

5. si los envíos están prendidos (``DELIVERIES_ENABLED``), manda el reporte
   según las reglas de la pantalla «Envíos» (ADR-0039).

No hace: no decide horarios (eso es ``celery_app``).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.adapters.llm.factory import MissingLLMKeyError, build_summarizer, llm_info
from app.adapters.persistence.concepts_repository import PostgresConceptRepository
from app.adapters.persistence.provider_queries_repository import PostgresProviderQueryLog
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.persistence.reports_repository import PostgresReportStore
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.adapters.reports.render import ReportRenderer
from app.adapters.reports.static_map import PostgisStaticMap
from app.application.audit import Actor
from app.application.clock import MEXICO_CITY
from app.application.use_cases.automatic_run import AutomaticProfile, PrepareAutomaticRun
from app.application.use_cases.plan_search import PlanSearch
from app.application.use_cases.reports import BuildReport, LLMPrices, ReportFormat
from app.application.use_cases.run_search import SearchReport
from app.application.use_cases.start_search import StartSearch
from app.core.config import Settings
from app.domain.schedule import parse_run_hours, run_slot
from app.domain.sources import parse_sources
from app.worker.delivery_jobs import deliver_run
from app.worker.search_jobs import build_providers, run_search_job

logger = logging.getLogger(__name__)


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
        run_hours=parse_run_hours(settings.automatic_run_hours),
        margin_minutes=settings.automatic_window_margin_minutes,
    )


def report_file_name(scheduled_for: datetime) -> str:
    """Nombre del PDF de una corrida: ``fgr_2026-10-26_0700.pdf``.

    Args:
        scheduled_for: Hora programada (CDMX).

    Returns:
        El nombre, ordenable por fecha en cualquier explorador de archivos.
    """
    return f"fgr_{scheduled_for:%Y-%m-%d_%H%M}.pdf"


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


async def run_automatic_job(settings: Settings, now: datetime | None = None) -> AutomaticRunSummary:
    """Corre una corrida automática completa.

    Args:
        settings: Configuración.
        now: Momento de la corrida (por defecto, ahora); define a qué horario
            pertenece y qué días cubre.

    Returns:
        La búsqueda creada, su resultado y la ruta del PDF.

    Raises:
        AutomaticRunConfigError: Si falta el concepto o la región del perfil.
        LLMNotConfiguredError, ServiceUnavailableError: Ver ``StartSearch``.
    """
    settings = automatic_settings(settings)
    local_now = (now or datetime.now(UTC)).astimezone(MEXICO_CITY)
    slot = run_slot(local_now, parse_run_hours(settings.automatic_run_hours))
    engine = create_async_engine(settings.database_url())
    try:
        search_id = await _create(settings, engine, local_now, slot)
    finally:
        await engine.dispose()
    logger.info(
        "Corrida automática creada",
        extra={"search_id": str(search_id), "corrida": slot.isoformat()},
    )
    report = await run_search_job(settings, search_id)
    pdf_path = await _save_report(settings, search_id, slot)
    await deliver_run(settings, search_id, slot)
    return AutomaticRunSummary(search_id, slot, report, pdf_path)


async def _create(
    settings: Settings, engine: AsyncEngine, local_now: datetime, slot: datetime
) -> UUID:
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
    # Solo de la corrida programada anterior a esta (run_window).
    request = await PrepareAutomaticRun(concepts, regions, profile).request(slot)
    started = await StartSearch(
        planner, PostgresSearchStore(engine), _RunsHere(), settings.max_queries_per_search
    ).execute(request)
    return started.search_id


async def _save_report(settings: Settings, search_id: UUID, slot: datetime) -> Path | None:
    """Arma el reporte de la corrida y guarda su PDF; si falla, la corrida sigue valiendo."""
    engine = create_async_engine(settings.database_url())
    try:
        store = PostgresReportStore(engine)
        data = await _builder(settings, engine, store).execute(
            search_id, ReportFormat.PDF, Actor(settings.automatic_user)
        )
        # WeasyPrint es lento y síncrono (~1 s por 50 notas): en otro hilo.
        pdf = await asyncio.to_thread(ReportRenderer().pdf, data)
        path = settings.reports_dir / report_file_name(slot)
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
