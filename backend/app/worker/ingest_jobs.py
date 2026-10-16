"""Arma y corre la ingesta completa con piezas reales (ADR-0013).

Es el punto donde se juntan las fuentes, la base y los casos de uso. Lo
usan las tareas de Celery (``app.worker.tasks``) y el comando
``make ingesta``, para que los dos hagan exactamente lo mismo.

Respeta los interruptores de la configuración: ``GDELT_GKG_ENABLED``,
``GDELT_NGRAMS_ENABLED`` y ``MEDIA_RSS_ENABLED`` (y, dentro de RSS, solo los
medios con ``activo=si``).

No hace: no decide cuándo correr (eso es ``celery beat``) ni muestra nada.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.ingest.factory import (
    build_gkg_source,
    build_ngrams_source,
    build_rss_source,
)
from app.adapters.ingest.media_rss import read_feeds
from app.adapters.persistence.news_index_repository import (
    PostgresIngestRunLog,
    PostgresNewsIndex,
)
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.application.use_cases.ingest import (
    IngestGdeltGkg,
    IngestGdeltNgrams,
    IngestMediaRss,
    IngestReport,
    PurgeNewsIndex,
    PurgeReport,
    recent_minutes,
)
from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class IngestSummary:
    """Resultado de una corrida completa.

    Attributes:
        gdelt: Reporte del GKG de GDELT, o ``None`` si está apagado.
        media: Un reporte por medio activo (vacío si RSS está apagado).
        ngrams: Un reporte por minuto de ngramas bajado (vacío si están
            apagados o no había minutos nuevos).
    """

    gdelt: IngestReport | None
    media: list[IngestReport] = field(default_factory=list)
    ngrams: list[IngestReport] = field(default_factory=list)

    @property
    def reports(self) -> list[IngestReport]:
        """Todos los reportes, en el orden en que corrieron las fuentes."""
        return [*([self.gdelt] if self.gdelt else []), *self.media, *self.ngrams]


async def run_ingest(settings: Settings) -> IngestSummary:
    """Corre una vez la ingesta de todas las fuentes encendidas.

    Args:
        settings: Configuración.

    Returns:
        Qué pasó con cada fuente. Los errores de una fuente quedan en su
        reporte (y en ``ingest_runs``); no detienen a las demás.
    """
    engine = create_async_engine(settings.database_url())
    index = PostgresNewsIndex(engine)
    runs = PostgresIngestRunLog(engine)
    gdelt: IngestReport | None = None
    media: list[IngestReport] = []
    ngrams: list[IngestReport] = []
    try:
        if settings.gdelt_gkg_enabled:
            source = build_gkg_source(settings)
            try:
                gdelt = await IngestGdeltGkg(source, index, runs).run()
            finally:
                await source.aclose()
        if settings.media_rss_enabled:
            rss = build_rss_source(settings)
            try:
                media = await IngestMediaRss(rss, read_feeds(), index, runs).run()
            finally:
                await rss.aclose()
        if settings.gdelt_ngrams_enabled:
            terms = await PostgresRegionRepository(engine).state_terms()
            ngrams_source = build_ngrams_source(settings, terms)
            minutes = recent_minutes(
                datetime.now(UTC),
                settings.ngrams_lookback_minutes,
                settings.ngrams_delay_minutes,
            )
            try:
                ngrams = await IngestGdeltNgrams(ngrams_source, index, runs).run(minutes)
            finally:
                await ngrams_source.aclose()
    finally:
        await engine.dispose()
    return IngestSummary(gdelt=gdelt, media=media, ngrams=ngrams)


async def run_purge(settings: Settings) -> PurgeReport:
    """Aplica las retenciones del índice: notas completas y frases del cuerpo.

    Args:
        settings: Configuración.

    Returns:
        Cuántas notas se borraron y a cuántas se les quitó el cuerpo.
    """
    engine = create_async_engine(settings.database_url())
    try:
        return await PurgeNewsIndex(
            PostgresNewsIndex(engine),
            settings.news_index_retention_days,
            settings.news_body_retention_days,
        ).run()
    finally:
        await engine.dispose()
