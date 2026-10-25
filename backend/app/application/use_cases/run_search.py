"""Correr una búsqueda completa: las 8 etapas del pipeline (especificación §9).

1. **Planear:** ``build_queries`` por concepto y proveedor, con los conceptos
   **copiados** al crear la búsqueda (editar un concepto no cambia una
   búsqueda ya pedida).
2. **Consultar:** ``ExecuteQueries`` (presupuesto, caché, tope mensual y
   registro en ``provider_queries``).
3. **Deduplicar:** ``dedupe`` y guardar las notas en ``articles``. La misma
   nota ya guardada con otro link (``match_known``, ADR-0025) se reutiliza
   en lugar de crear otra. Si una nota ya se enriqueció con la misma versión
   del prompt y los mismos conceptos, se reutiliza (caché de §10): no se
   vuelve a bajar ni a pagar.
4. **Extraer texto:** ``ExtractTexts``; si falla, título + fragmento
   (``fallback``).
5. **Enriquecer:** la IA (``LLMPort``), hasta ``LLM_MAX_ARTICLES_PER_SEARCH``
   notas; las demás quedan sin enriquecer y se cuenta cuántas.
6. **Geolocalizar:** ``GeocodeMentions`` con la región buscada para
   desempatar.
7. **Filtrar por región:** ``in_region`` por la clave INEGI o el país. Las
   de fuera **no se borran**.
8. **Cerrar:** junta en historias las notas del mismo hecho (ADR-0026),
   estado final (``final_status``), créditos, tokens y costo, y
   la bitácora.

Un error en una nota va a ``processing_errors`` y la búsqueda sigue. Cada
etapa actualiza ``searches.progress`` para mostrar avance real.

No hace: no decide cuándo correr (lo lanza la tarea de Celery o el comando
``make buscar``) ni muestra nada.
"""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from app.application.audit import Actor
from app.application.ports.geocoding import GazetteerPort
from app.application.ports.llm import (
    EnrichmentError,
    EnrichmentRequest,
    EnrichmentResult,
    LLMPort,
)
from app.application.ports.providers import NewsProviderPort
from app.application.ports.regions import RegionRepositoryPort
from app.application.ports.search_store import (
    ArticleStorePort,
    ProcessingErrorRecord,
    SearchClosing,
    SearchConcept,
    SearchResultRow,
    SearchStorePort,
    StoredArticle,
    StoredSearch,
)
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionResult
from app.application.use_cases.extraction import ArticleText, ExtractTexts
from app.application.use_cases.geocoding import GeocodeMentions, search_area
from app.application.use_cases.stories import GroupStories
from app.domain.dedupe import DedupedArticle, TitleSimilarity, dedupe, match_known
from app.domain.enrichment import ConceptBrief, LLMUsage, text_for_llm
from app.domain.errors import DomainError, NotFoundError, ProviderError
from app.domain.extraction import ExtractionStatus
from app.domain.geocoding import Place, Resolution
from app.domain.queries import DateWindow, PlannedQuery, Provider, QueryPlace, place_for
from app.domain.query_builder import build_queries
from app.domain.search import SearchStatus, Stage, StageCount, final_status, in_region

# Cada cuántas notas enriquecidas se actualiza el avance: suficiente para ver
# que se mueve sin escribir en la base por cada nota.
ENRICH_PROGRESS_EVERY = 10
# Errores de la IA que se citan en el resumen de la búsqueda.
SUMMARY_SAMPLE_ERRORS = 1
# Sin tokens (es inmutable: se puede compartir como valor por defecto).
NO_USAGE = LLMUsage(0, 0)


class SearchNotFoundError(NotFoundError):
    """La búsqueda pedida no existe."""

    code = "search_not_found"


@dataclass(frozen=True, slots=True)
class PipelineLimits:
    """Límites y precios de la configuración (``.env``).

    Attributes:
        max_llm_articles: ``LLM_MAX_ARTICLES_PER_SEARCH``.
        llm_concurrency: ``LLM_CONCURRENCY``.
        price_input_per_million: Precio de entrada del modelo elegido.
        price_output_per_million: Precio de salida del modelo elegido.
    """

    max_llm_articles: int
    llm_concurrency: int
    price_input_per_million: float
    price_output_per_million: float


@dataclass(frozen=True, slots=True)
class SearchReport:
    """Resumen de una búsqueda terminada.

    Attributes:
        search_id: Id.
        status: Estado final.
        articles: Notas distintas encontradas.
        reused: Notas que ya estaban enriquecidas (no se pagaron).
        enriched: Notas enriquecidas en esta búsqueda.
        enrich_failed: Notas en las que falló la IA.
        fallback: Notas procesadas con título + fragmento.
        skipped_by_cap: Notas sin enriquecer por el tope por búsqueda.
        in_region: Notas cuya ubicación principal cae en la región.
        out_of_region: Notas ubicadas fuera de la región.
        unlocated: Notas sin ubicación.
        credits_used: Créditos de SearchApi.
        llm_usage: Tokens de la IA.
        llm_cost_usd: Costo estimado de la IA.
        error_summary: Qué falló, si algo falló.
    """

    search_id: UUID
    status: SearchStatus
    articles: int = 0
    reused: int = 0
    enriched: int = 0
    enrich_failed: int = 0
    fallback: int = 0
    skipped_by_cap: int = 0
    in_region: int = 0
    out_of_region: int = 0
    unlocated: int = 0
    credits_used: int = 0
    llm_usage: LLMUsage = NO_USAGE
    llm_cost_usd: float = 0.0
    error_summary: str | None = None


def plan_queries(
    concepts: Sequence[SearchConcept],
    place: QueryPlace,
    window: DateWindow,
    providers: Sequence[Provider],
) -> list[PlannedQuery]:
    """Consultas de una búsqueda: las de cada concepto con cada proveedor.

    Args:
        concepts: Conceptos de la búsqueda.
        place: Cómo se nombra la región (``place_for``).
        window: Rango de fechas.
        providers: Proveedores disponibles.

    Returns:
        Todas las consultas, concepto por concepto.

    Raises:
        ConceptValidationError: Si un concepto no tiene palabras clave.
        QueryTooLongError: Si una palabra clave no cabe en el límite.
    """
    return [q for c in concepts for q in build_queries(c, place, window, providers)]


@dataclass(slots=True)
class _Work:
    """Una nota en su paso por el pipeline."""

    item: DedupedArticle
    stored: StoredArticle
    text: ArticleText | None = None
    resolutions: list[Resolution] = field(default_factory=list)
    primary: Place | None = None
    result: EnrichmentResult | None = None


@dataclass(slots=True)
class _Tally:
    """Conteos que se van llenando y se guardan como ``progress``."""

    stage: Stage = Stage.PLAN
    stages: dict[Stage, StageCount] = field(default_factory=dict)
    extra: dict[str, int] = field(default_factory=dict)
    usage: LLMUsage = NO_USAGE
    errors: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "stages": {
                s.value: {"total": c.total, "failed": c.failed} for s, c in self.stages.items()
            },
            **self.extra,
        }


class RunSearch:
    """Corre una búsqueda guardada de principio a fin."""

    def __init__(  # noqa: PLR0913 — una pieza por etapa del pipeline, todo por nombre (*)
        self,
        *,
        searches: SearchStorePort,
        articles: ArticleStorePort,
        regions: RegionRepositoryPort,
        gazetteer: GazetteerPort,
        providers: Mapping[Provider, NewsProviderPort],
        executor: ExecuteQueries,
        extractor: ExtractTexts,
        llm: LLMPort,
        geocoder: GeocodeMentions,
        similarity: TitleSimilarity,
        limits: PipelineLimits,
        stories: GroupStories | None = None,
        log_progress: Callable[[UUID, Mapping[str, object]], None] = lambda _id, _p: None,
    ) -> None:
        """Recibe una pieza por etapa.

        Args:
            searches: Fila de ``searches``.
            articles: Notas y su procesamiento.
            regions: Catálogo (para nombrar la región en la consulta).
            gazetteer: Catálogo (para la región buscada como ``Place``).
            providers: Proveedores; solo se planea con los configurados.
            executor: Ejecuta las consultas.
            extractor: Lee el texto de las notas.
            llm: La IA.
            geocoder: Resuelve las menciones de lugar.
            similarity: Similitud de títulos (rapidfuzz en producción).
            limits: Topes y precios.
            stories: Agrupa en historias las notas encontradas (F12.1c); sin
                él, no se agrupa.
            log_progress: Aviso de avance (el comando lo muestra en pantalla).
        """
        self._searches = searches
        self._articles = articles
        self._regions = regions
        self._gazetteer = gazetteer
        self._providers = providers
        self._executor = executor
        self._extractor = extractor
        self._llm = llm
        self._geocoder = geocoder
        self._similarity = similarity
        self._limits = limits
        self._stories = stories
        self._log_progress = log_progress

    def available_providers(self) -> list[Provider]:
        """Proveedores con lo necesario para consultar, en orden.

        Returns:
            Los configurados (SearchApi sin llave no cuenta).
        """
        return [p for p, adapter in self._providers.items() if adapter.is_configured()]

    def _sources_of(self, search: StoredSearch) -> list[Provider]:
        """Las fuentes elegidas que siguen configuradas (todas, en búsquedas viejas)."""
        available = self.available_providers()
        if not search.providers:
            return available
        return [p for p in available if p in search.providers]

    async def run(self, search_id: UUID) -> SearchReport:
        """Corre la búsqueda.

        Args:
            search_id: Búsqueda creada en ``pending``.

        Returns:
            El resumen.

        Raises:
            SearchNotFoundError: Si no existe.
        """
        search = await self._searches.load(search_id)
        if search is None:
            raise SearchNotFoundError(f"No existe la búsqueda {search_id}.")
        await self._searches.start(search_id)
        tally = _Tally()
        try:
            searched, queries = await self._plan(search)
            await self._progress(search_id, tally, Stage.QUERY)
            execution = await self._executor.execute(queries, search_id)
        except DomainError as error:
            tally.errors.append(error.message)
            await self._searches.record_error(
                ProcessingErrorRecord(search_id, tally.stage, type(error).__name__, error.message)
            )
            return await self._close(search, tally, None, [])
        failed_queries = sum(1 for o in execution.outcomes if o.status != "ok")
        tally.stages[Stage.QUERY] = StageCount(Stage.QUERY, len(queries), failed_queries)
        tally.errors.extend(
            f"{o.query.provider.value}: {o.message}" for o in execution.outcomes if o.message
        )
        if failed_queries == len(execution.outcomes):
            return await self._close(search, tally, execution, [])
        work = await self._dedupe(search, tally, execution)
        pending = await self._extract(search, tally, work)
        await self._enrich(search, tally, pending)
        await self._geolocate(search, tally, work, searched)
        return await self._close(search, tally, execution, work, searched)

    async def _progress(self, search_id: UUID, tally: _Tally, stage: Stage) -> None:
        tally.stage = stage
        progress = tally.as_json()
        await self._searches.set_progress(search_id, progress)
        self._log_progress(search_id, progress)

    async def _plan(self, search: StoredSearch) -> tuple[Place, list[PlannedQuery]]:
        facts = await self._regions.place_facts(search.region_id)
        searched = await self._gazetteer.by_code(search.region_code)
        if facts is None or searched is None:
            raise NotFoundError(f"No existe la región {search.region_code} en el catálogo.")
        searched = await search_area(self._gazetteer, searched)
        window = DateWindow.between(search.date_from, search.date_to)
        queries = plan_queries(search.concepts, place_for(facts), window, self._sources_of(search))
        return searched, queries

    async def _dedupe(
        self, search: StoredSearch, tally: _Tally, execution: ExecutionResult
    ) -> list[_Work]:
        await self._progress(search.search_id, tally, Stage.DEDUPE)
        unique = dedupe(execution.articles, self._similarity)
        # Nivel 2 de duplicados (ADR-0025): la misma nota que ya se guardó en
        # otra búsqueda con otro link se reutiliza, con su IA ya pagada.
        candidates = await self._articles.known_like(unique)
        for item, known in zip(unique, candidates, strict=True):
            match = match_known(item, known, self._similarity)
            item.known_id = match.article_id if match else None
        stored = await self._articles.upsert(unique)
        tally.extra["articles"] = len(unique)
        tally.extra["known"] = sum(1 for item in unique if item.known_id is not None)
        return [_Work(item, s) for item, s in zip(unique, stored, strict=True)]

    async def _extract(self, search: StoredSearch, tally: _Tally, work: list[_Work]) -> list[_Work]:
        """Lee el texto de las notas que hay que enriquecer (respetando el tope)."""
        concept_ids = frozenset(c.concept_id for c in search.concepts)
        version = self._llm.prompt_version
        fresh = [w for w in work if not w.stored.reusable_for(version, concept_ids)]
        tally.extra["reused"] = len(work) - len(fresh)
        pending = fresh[: self._limits.max_llm_articles]
        tally.extra["skipped_by_cap"] = len(fresh) - len(pending)
        await self._progress(search.search_id, tally, Stage.EXTRACT)
        texts = await self._extractor.run([w.item for w in pending])
        for w, text in zip(pending, texts, strict=True):
            w.text = text
            await self._articles.save_text(w.stored.article_id, text.text)
        tally.extra["fallback"] = sum(
            1 for w in pending if w.text and w.text.text.status is ExtractionStatus.FALLBACK
        )
        # Usar título + fragmento no es una falla: la nota se procesa igual.
        tally.stages[Stage.EXTRACT] = StageCount(Stage.EXTRACT, len(pending), 0)
        return pending

    async def _enrich(self, search: StoredSearch, tally: _Tally, pending: list[_Work]) -> None:
        await self._progress(search.search_id, tally, Stage.ENRICH)
        briefs = [
            ConceptBrief(c.concept_id, c.name, c.description, c.keywords) for c in search.concepts
        ]
        semaphore = asyncio.Semaphore(self._limits.llm_concurrency)
        failures: list[str] = []
        done = 0

        async def one(w: _Work, text: ArticleText) -> None:
            nonlocal done
            article = w.item.article
            request = EnrichmentRequest(
                article.title, text_for_llm(text.text.text), article.published_at, briefs
            )
            try:
                async with semaphore:
                    w.result = await self._llm.enrich(request)
            except EnrichmentError as error:
                tally.usage += error.usage
                await self._enrich_failed(search, w, error, str(error), failures)
                return
            except ProviderError as error:
                await self._enrich_failed(search, w, error, error.message, failures)
                return
            tally.usage += w.result.usage
            done += 1
            if done % ENRICH_PROGRESS_EVERY == 0:
                tally.extra["enriched"] = done
                await self._progress(search.search_id, tally, Stage.ENRICH)

        await asyncio.gather(*(one(w, w.text) for w in pending if w.text is not None))
        tally.extra["enriched"] = done
        tally.stages[Stage.ENRICH] = StageCount(Stage.ENRICH, len(pending), len(failures))
        if failures:
            sample = "; ".join(failures[:SUMMARY_SAMPLE_ERRORS])
            tally.errors.append(
                f"La IA falló en {len(failures)} de {len(pending)} notas ({sample})."
            )

    async def _enrich_failed(
        self,
        search: StoredSearch,
        w: _Work,
        error: Exception,
        message: str,
        failures: list[str],
    ) -> None:
        failures.append(message)
        await self._articles.mark_enrichment_failed(w.stored.article_id)
        await self._searches.record_error(
            ProcessingErrorRecord(
                search.search_id,
                Stage.ENRICH,
                type(error).__name__,
                message,
                w.stored.article_id,
                {"url": w.item.article.url},
            )
        )

    async def _geolocate(
        self, search: StoredSearch, tally: _Tally, work: list[_Work], searched: Place
    ) -> None:
        """Resuelve los lugares de las notas recién enriquecidas y lee los de las reutilizadas."""
        await self._progress(search.search_id, tally, Stage.GEOCODE)
        geocoded = 0
        for w in work:
            if w.result is not None:
                w.resolutions = await self._geocoder.run(w.result.enrichment.locations, searched)
                await self._articles.save_enrichment(w.stored.article_id, w.result, w.resolutions)
                w.primary = next((r.place for r in w.resolutions if r.is_primary), None)
                geocoded += 1
            elif w.stored.primary_code is not None:
                w.primary = await self._gazetteer.by_code(w.stored.primary_code)
        tally.stages[Stage.GEOCODE] = StageCount(Stage.GEOCODE, geocoded, 0)

    async def _group_stories(self, search: StoredSearch, tally: _Tally, work: list[_Work]) -> None:
        """Junta en historias las notas encontradas (F12.1c, ADR-0026).

        Agrupar es un extra para el analista: si falla, la búsqueda sigue con
        su estado y el error queda en ``processing_errors``.
        """
        if self._stories is None or not work:
            return
        try:
            tally.extra["stories_changed"] = await self._stories.run(
                [w.stored.article_id for w in work]
            )
        except Exception as error:
            await self._searches.record_error(
                ProcessingErrorRecord(
                    search.search_id, Stage.CLOSE, type(error).__name__, f"Historias: {error}"
                )
            )

    async def _close(
        self,
        search: StoredSearch,
        tally: _Tally,
        execution: ExecutionResult | None,
        work: list[_Work],
        searched: Place | None = None,
    ) -> SearchReport:
        await self._progress(search.search_id, tally, Stage.FILTER)
        rows: list[SearchResultRow] = []
        located = {True: 0, False: 0, None: 0}
        for w in work:
            inside = in_region(w.primary, searched) if searched is not None else None
            located[inside] += 1
            rows.extend(
                SearchResultRow(w.stored.article_id, s.provider, s.rank, inside)
                for s in w.item.sightings
            )
        if rows:
            await self._articles.link_results(search.search_id, rows)
        await self._group_stories(search, tally, work)
        tally.extra.update(
            {
                "in_region": located[True],
                "out_of_region": located[False],
                "unlocated": located[None],
            }
        )
        outcomes = execution.outcomes if execution else ()
        ok = sum(1 for o in outcomes if o.status == "ok")
        status = final_status(ok, len(outcomes) - ok, tuple(tally.stages.values()))
        cost = tally.usage.cost_usd(
            self._limits.price_input_per_million, self._limits.price_output_per_million
        )
        summary = " ".join(tally.errors) or None
        await self._progress(search.search_id, tally, Stage.CLOSE)
        spent = execution.credits_used if execution else 0
        await self._searches.finish(
            search.search_id,
            SearchClosing(
                status=status,
                progress=tally.as_json(),
                credits_used=spent,
                llm_usage=tally.usage,
                llm_cost_usd=cost,
                results_count=len(work),
                error_summary=summary,
                queries_executed=tuple(
                    {
                        "provider": o.query.provider.value,
                        "text": o.query.text,
                        "status": o.status,
                        "credits": o.credits,
                        "results": len(o.articles),
                    }
                    for o in outcomes
                ),
            ),
            Actor(search.user_id),
        )
        return SearchReport(
            search_id=search.search_id,
            status=status,
            articles=len(work),
            reused=tally.extra.get("reused", 0),
            enriched=tally.extra.get("enriched", 0),
            enrich_failed=tally.stages.get(Stage.ENRICH, StageCount(Stage.ENRICH, 0, 0)).failed,
            fallback=tally.extra.get("fallback", 0),
            skipped_by_cap=tally.extra.get("skipped_by_cap", 0),
            in_region=located[True],
            out_of_region=located[False],
            unlocated=located[None],
            credits_used=spent,
            llm_usage=tally.usage,
            llm_cost_usd=cost,
            error_summary=summary,
        )
