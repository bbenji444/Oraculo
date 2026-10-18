"""Armar el reporte de una búsqueda y exportar sus notas (especificación §15, ADR-0018).

``BuildReport`` junta todo lo que lleva el PDF:
- la portada;
- el resumen ejecutivo (el guardado, o uno nuevo de la IA que se guarda);
- los conteos por subregión;
- el mapa;
- las notas relevantes;
- los proveedores con sus créditos.

``ExportSearch`` junta las notas para el CSV y el GeoJSON. Los dos dejan un
``report.generated`` en la bitácora.

No hace: no dibuja HTML ni PDF (eso son los adaptadores de ``reports/``) ni
corre búsquedas.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.application.audit import Actor
from app.application.pagination import TimeCursor
from app.application.ports.llm import SummarizerPort, SummaryError, SummaryNote, SummaryRequest
from app.application.ports.regions import RegionRepositoryPort
from app.application.ports.reports import (
    MapPoint,
    ProviderUsage,
    ReportMapPort,
    ReportStorePort,
    StoredSummary,
    SubregionCount,
)
from app.application.ports.search_reads import (
    ArticleFilters,
    ArticleItem,
    ArticleReaderPort,
    SearchDetail,
    SearchReaderPort,
)
from app.application.use_cases.search_reads import MAX_ARTICLE_PAGE_SIZE, GetSearch
from app.domain.aggregates import AggregateLevel, aggregate
from app.domain.errors import ProviderError, RegionNotFoundError, SearchNotFinishedError
from app.domain.geocoding import Precision
from app.domain.region import Region
from app.domain.reports import is_inside, subregion_level

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]

# Lo que se lee en la portada cuando no hay resumen ejecutivo.
NO_NOTES_NOTICE = "No hay notas relevantes: no hay nada que resumir."
NO_LLM_NOTICE = "No se generó el resumen automático: falta la llave de la IA en el servidor."
FAILED_NOTICE = "No se pudo generar el resumen automático. El resto del reporte está completo."
# Ubicaciones que el mapa dibuja con anillo punteado (solo estado o país, §14.2).
_COARSE = frozenset({Precision.STATE.value, Precision.COUNTRY.value})


class ReportFormat(StrEnum):
    """Formatos de salida (§13: ``report`` y ``export``)."""

    PDF = "pdf"
    HTML = "html"
    CSV = "csv"
    GEOJSON = "geojson"


@dataclass(frozen=True, slots=True)
class LLMPrices:
    """Precios de la IA del resumen, para guardar su costo.

    Attributes:
        provider: ``openai`` o ``gemini``.
        input_per_million: Dólares por millón de tokens de entrada.
        output_per_million: Dólares por millón de tokens de salida.
    """

    provider: str
    input_per_million: float
    output_per_million: float


@dataclass(frozen=True, slots=True)
class ReportData:
    """Todo lo que lleva el reporte, listo para la plantilla.

    Attributes:
        search: La búsqueda (conceptos, fechas, créditos y costo de la IA).
        region: Región buscada.
        breadcrumb: Migas de pan ("México › Jalisco").
        level: Nivel de las subregiones de la tabla y el mapa.
        counts: Notas por subregión de la región, de más a menos.
        outside: Notas relevantes ubicadas fuera de la región.
        coarser: Notas de la región ubicadas con menos precisión que el nivel.
        unlocated: Notas sin ubicación.
        articles: Notas relevantes, de la más reciente a la más vieja.
        summary: Resumen ejecutivo, o ``None``.
        summary_model: Modelo que lo escribió.
        summary_notice: Por qué no hay resumen, si no lo hay.
        providers: Uso de cada proveedor.
        map_svg: Mapa estático (``<svg>``).
        generated_at: Cuándo se generó (UTC).
        generated_by: Quién lo pidió.
    """

    search: SearchDetail
    region: Region
    breadcrumb: str
    level: AggregateLevel
    counts: tuple[SubregionCount, ...]
    outside: int
    coarser: int
    unlocated: int
    articles: tuple[ArticleItem, ...]
    summary: str | None
    summary_model: str | None
    summary_notice: str | None
    providers: tuple[ProviderUsage, ...]
    map_svg: str
    generated_at: datetime
    generated_by: str


@dataclass(frozen=True, slots=True)
class ExportData:
    """Las notas de una búsqueda para el CSV o el GeoJSON.

    Attributes:
        search: La búsqueda.
        breadcrumb: Migas de pan de la región.
        articles: Notas relevantes, de la más reciente a la más vieja.
        generated_at: Cuándo se generó (UTC).
    """

    search: SearchDetail
    breadcrumb: str
    articles: tuple[ArticleItem, ...]
    generated_at: datetime


async def _finished_search(searches: SearchReaderPort, search_id: UUID) -> SearchDetail:
    search = await GetSearch(searches).execute(search_id)
    if not search.status.is_finished:
        raise SearchNotFinishedError(
            "La búsqueda todavía no termina: su reporte y sus datos se piden al terminar.",
            {"id": str(search_id), "status": search.status.value},
        )
    return search


async def _region_and_breadcrumb(
    regions: RegionRepositoryPort, region_id: int
) -> tuple[Region, str]:
    region = await regions.get(region_id)
    if region is None:
        raise RegionNotFoundError("No existe la región de la búsqueda.", {"id": region_id})
    names = [a.name for a in await regions.ancestors(region_id)]
    return region, " › ".join([*names, region.display_name])


async def _relevant_articles(
    articles: ArticleReaderPort, search_id: UUID
) -> tuple[ArticleItem, ...]:
    # Se sigue el cursor: una búsqueda trae a lo más unas 150 notas (tope de
    # la IA), así que son una o dos páginas.
    found: list[ArticleItem] = []
    after: TimeCursor | None = None
    while True:
        page = await articles.search_articles(
            search_id, ArticleFilters(), after, MAX_ARTICLE_PAGE_SIZE
        )
        found.extend(page)
        if len(page) < MAX_ARTICLE_PAGE_SIZE:
            return tuple(found)
        after = TimeCursor(page[-1].published_at, str(page[-1].article_id))


class BuildReport:
    """Arma el reporte de una búsqueda terminada."""

    def __init__(  # noqa: PLR0913 — un puerto por fuente del reporte, todo por nombre (*)
        self,
        *,
        searches: SearchReaderPort,
        articles: ArticleReaderPort,
        regions: RegionRepositoryPort,
        store: ReportStorePort,
        static_map: ReportMapPort,
        summarizer: SummarizerPort | None,
        prices: LLMPrices | None,
        clock: Clock,
    ) -> None:
        """Recibe los puertos.

        Args:
            searches: Lecturas de búsquedas.
            articles: Lecturas de notas.
            regions: Catálogo geográfico (migas de pan y nivel).
            store: Resumen guardado, proveedores y bitácora.
            static_map: Mapa estático.
            summarizer: IA del resumen, o ``None`` si falta su llave.
            prices: Precios de esa IA (para guardar el costo).
            clock: Hora actual (UTC).
        """
        self._searches = searches
        self._articles = articles
        self._regions = regions
        self._store = store
        self._map = static_map
        self._summarizer = summarizer
        self._prices = prices
        self._clock = clock

    async def execute(
        self, search_id: UUID, report_format: ReportFormat, actor: Actor
    ) -> ReportData:
        """Arma el reporte y lo deja en la bitácora.

        Args:
            search_id: Búsqueda.
            report_format: ``pdf`` o ``html`` (va a la bitácora).
            actor: Quién lo pide.

        Returns:
            Todo lo que lleva el reporte.

        Raises:
            SearchNotFoundError: Si la búsqueda no existe.
            SearchNotFinishedError: Si todavía corre.
            RegionNotFoundError: Si su región ya no está en el catálogo.
        """
        search = await _finished_search(self._searches, search_id)
        region, breadcrumb = await _region_and_breadcrumb(self._regions, search.region_id)
        articles = await _relevant_articles(self._articles, search_id)
        level = subregion_level(region.level, region.code)
        counts, outside, coarser, unlocated = await self._counts(search_id, region, level)
        points = [
            MapPoint(a.primary.lon, a.primary.lat, a.primary.precision in _COARSE)
            for a in articles
            if a.primary and a.primary.lon is not None and a.primary.lat is not None
        ]
        summary, notice = await self._summary(search, breadcrumb, articles, actor)
        data = ReportData(
            search=search,
            region=region,
            breadcrumb=breadcrumb,
            level=level,
            counts=counts,
            outside=outside,
            coarser=coarser,
            unlocated=unlocated,
            articles=articles,
            summary=summary.text if summary else None,
            summary_model=summary.model if summary else None,
            summary_notice=notice,
            providers=tuple(await self._store.provider_usage(search_id)),
            map_svg=await self._map.render(region, level, counts, points),
            generated_at=self._clock(),
            generated_by=actor.user_id,
        )
        await self._store.record_generated(search_id, report_format.value, actor)
        return data

    async def _counts(
        self, search_id: UUID, region: Region, level: AggregateLevel
    ) -> tuple[tuple[SubregionCount, ...], int, int, int]:
        notes = await self._articles.note_locations(search_id, ArticleFilters())
        unlocated = sum(1 for n in notes if n.code is None)
        inside = [n for n in notes if is_inside(n, region.code, region.level)]
        # Solo lo de dentro se sube a subregiones; lo que dentro de la región es
        # menos preciso que el nivel ("solo Jalisco") queda en ``coarser``.
        result = aggregate(inside, level)
        names = {
            r.code: r.name for r in await self._articles.regions_by_code(sorted(result.counts))
        }
        counts = sorted(
            (
                SubregionCount(code, names.get(code, code), count)
                for code, count in result.counts.items()
            ),
            key=lambda c: (-c.count, c.name),
        )
        outside = len(notes) - len(inside) - unlocated
        return tuple(counts), outside, result.coarser, unlocated

    async def _summary(
        self,
        search: SearchDetail,
        breadcrumb: str,
        articles: tuple[ArticleItem, ...],
        actor: Actor,
    ) -> tuple[StoredSummary | None, str | None]:
        stored = await self._store.summary(search.search_id)
        if stored is not None:
            return stored, None
        notes = [
            SummaryNote(a.title, a.summary, a.primary.place if a.primary else None, a.published_at)
            for a in articles
            if a.summary
        ]
        if not notes:
            return None, NO_NOTES_NOTICE
        if self._summarizer is None or self._prices is None:
            return None, NO_LLM_NOTICE
        request = SummaryRequest(
            [c.name for c in search.concepts],
            breadcrumb,
            search.date_from,
            search.date_to,
            notes,
        )
        try:
            result = await self._summarizer.summarize(request)
        except (SummaryError, ProviderError) as error:
            # El reporte sale igual, con un aviso en lugar del resumen (ADR-0018).
            logger.warning(
                "No se pudo generar el resumen ejecutivo",
                extra={"search_id": str(search.search_id), "error_type": type(error).__name__},
            )
            return None, FAILED_NOTICE
        stored = StoredSummary(
            text=result.text,
            provider=self._prices.provider,
            model=result.model,
            prompt_version=result.prompt_version,
            usage=result.usage,
            cost_usd=result.usage.cost_usd(
                self._prices.input_per_million, self._prices.output_per_million
            ),
        )
        await self._store.save_summary(search.search_id, stored, actor)
        return stored, None


class ExportSearch:
    """Junta las notas relevantes de una búsqueda terminada para descargarlas."""

    def __init__(
        self,
        searches: SearchReaderPort,
        articles: ArticleReaderPort,
        regions: RegionRepositoryPort,
        store: ReportStorePort,
        clock: Clock,
    ) -> None:
        """Recibe los puertos.

        Args:
            searches: Lecturas de búsquedas.
            articles: Lecturas de notas.
            regions: Catálogo geográfico (migas de pan).
            store: Bitácora.
            clock: Hora actual (UTC).
        """
        self._searches = searches
        self._articles = articles
        self._regions = regions
        self._store = store
        self._clock = clock

    async def execute(
        self, search_id: UUID, report_format: ReportFormat, actor: Actor
    ) -> ExportData:
        """Junta las notas y deja la exportación en la bitácora.

        Args:
            search_id: Búsqueda.
            report_format: ``csv`` o ``geojson`` (va a la bitácora).
            actor: Quién la pide.

        Returns:
            Las notas relevantes con los datos de la búsqueda.

        Raises:
            SearchNotFoundError: Si la búsqueda no existe.
            SearchNotFinishedError: Si todavía corre.
            RegionNotFoundError: Si su región ya no está en el catálogo.
        """
        search = await _finished_search(self._searches, search_id)
        _region, breadcrumb = await _region_and_breadcrumb(self._regions, search.region_id)
        articles = await _relevant_articles(self._articles, search_id)
        await self._store.record_generated(search_id, report_format.value, actor)
        return ExportData(search, breadcrumb, articles, self._clock())
