"""Correr una búsqueda completa: las 8 etapas del pipeline (especificación §9).

1. **Planear:** ``build_queries`` por concepto y proveedor, con los conceptos
   **copiados** al crear la búsqueda (editar un concepto no cambia una
   búsqueda ya pedida). Una búsqueda manual que termina hoy vuelve a ser
   «últimos N días» (``manual_window``, ADR-0113).
2. **Consultar:** ``ExecuteQueries`` (presupuesto, caché, tope mensual y
   registro en ``provider_queries``).
3. **Deduplicar:** ``dedupe`` y guardar las notas en ``articles``. La misma
   nota ya guardada con otro link (``match_known``, ADR-0025) se reutiliza
   en lugar de crear otra. Si una nota ya se enriqueció con la misma versión
   del prompt y los mismos conceptos, se reutiliza (caché de §10): no se
   vuelve a bajar ni a pagar. Antes de deduplicar, lo de un concepto abierto
   que no nombra lo pedido (entidad y tema) se descarta sin pagar
   (``_on_core``, ADR-0114).
4. **Extraer texto:** ``ExtractTexts``; si falla, título + fragmento
   (``fallback``). Una nota ya leída solo con título cuyo link de Google
   News cambió por el del medio se vuelve a leer (``_needs_body``, ADR-0115).
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
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from uuid import UUID

from app.application.audit import Actor
from app.application.clock import MEXICO_CITY, Today, mexico_city_today
from app.application.ports.geocoding import GazetteerPort
from app.application.ports.llm import (
    ClassificationError,
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
from app.application.use_cases.classify import ClassifyArticles
from app.application.use_cases.execute_queries import (
    ExecuteQueries,
    ExecutionResult,
    QueryOutcome,
)
from app.application.use_cases.extraction import ArticleText, ExtractTexts
from app.application.use_cases.geocoding import GeocodeMentions, search_area
from app.application.use_cases.stories import GroupStories
from app.domain.articles import RawArticle
from app.domain.concept import QueryMode
from app.domain.core_terms import (
    RAW_SECTION_KEY,
    WEB_ORGANIC_SECTION,
    CoreMatcher,
    CoreTerms,
    QueryOrigin,
    core_terms_for,
)
from app.domain.dedupe import (
    DedupedArticle,
    TitleSimilarity,
    canonical_url,
    dedupe,
    match_known,
    refreshes_link,
)
from app.domain.enrichment import ConceptBrief, LLMUsage, text_for_llm
from app.domain.errors import DomainError, NotFoundError, ProviderError
from app.domain.extraction import ExtractionStatus
from app.domain.geocoding import Place, Resolution
from app.domain.names import normalize_name
from app.domain.queries import (
    FULL_TEXT_PROVIDERS,
    DateWindow,
    PlannedQuery,
    Provider,
    QueryPlace,
    place_for,
)
from app.domain.query_builder import build_queries, manual_window
from app.domain.query_dialects import DIALECTS
from app.domain.result_dates import kept_by_window
from app.domain.schedule import RunWindow
from app.domain.search import SearchStatus, Stage, StageCount, final_status, in_region
from app.domain.subdivisions import TopicMatcher

# Cada cuántas notas enriquecidas se actualiza el avance: suficiente para ver
# que se mueve sin escribir en la base por cada nota.
ENRICH_PROGRESS_EVERY = 10
# Errores de la IA que se citan en el resumen de la búsqueda.
SUMMARY_SAMPLE_ERRORS = 1
# Sin tokens (es inmutable: se puede compartir como valor por defecto).
NO_USAGE = LLMUsage(0, 0)
# Títulos de muestra de las notas que no pasan el filtro de palabras
# (ADR-0114): bastan para auditar sin inflar ``searches.progress``, como las 5
# muestras que se piden antes de procesar datos reales (CLAUDE.md §2).
OFF_CORE_SAMPLES = 5
# Procedencias que se le cuentan a la IA por nota: una nota suele llegar por 1
# a 3 consultas; más líneas solo encarecen el prompt.
MAX_PROMPT_ORIGINS = 5


class SearchNotFoundError(NotFoundError):
    """La búsqueda pedida no existe."""

    code = "search_not_found"


def strict_window(search: StoredSearch) -> RunWindow:
    """El periodo estricto de una búsqueda: lo publicado fuera no cuenta.

    - Corrida automática: su ventana de horas (desde la corrida anterior).
    - Búsqueda manual: los días elegidos completos, de las 00:00 del primero
      a las 00:00 del día siguiente al último, en hora de la Ciudad de México.
      «Hoy» el 11/11 es solo el 11/11: ni ayer ni el 12.

    Args:
        search: La búsqueda guardada.

    Returns:
        La ventana.

    Example:
        >>> # date_from = date_to = 2026-11-11
        >>> # → 2026-11-11 00:00 CDMX hasta 2026-11-12 00:00 CDMX (sin incluir)
    """
    if search.time_window is not None:
        return search.time_window
    start = datetime.combine(search.date_from, time.min, MEXICO_CITY)
    end = datetime.combine(search.date_to + timedelta(days=1), time.min, MEXICO_CITY)
    return RunWindow(start, end)


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

    Las de un concepto abierto llevan lo que deben nombrar sus notas
    (``core_of``, ADR-0114); las de los exactos y el monitor FGR, no.

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
    planned: list[PlannedQuery] = []
    for c in concepts:
        core = core_of(c, place)
        planned.extend(
            q if core is None else replace(q, core=core)
            for q in build_queries(c, place, window, providers, topic_terms=c.topic_terms)
        )
    return planned


def core_of(concept: SearchConcept, place: QueryPlace) -> CoreTerms | None:
    """Lo que deben nombrar las notas de un concepto antes de pasar al juez (ADR-0114).

    Solo los conceptos abiertos (``query_mode=open``: los «como en Google» y
    las búsquedas rápidas). Los exactos y el monitor FGR se quedan como
    estaban (ADR-0109 D2).

    Args:
        concept: Concepto copiado en la búsqueda.
        place: Cómo se nombra la región: sus palabras no son tema.

    Returns:
        Entidades y raíces del tema, o ``None`` si no se filtra.
    """
    if concept.query_mode is not QueryMode.OPEN:
        return None
    place_names = (*place.terms, *place.required_terms, place.country.name)
    return core_terms_for(
        concept.description, concept.keywords, concept.required_terms, place_names
    )


@dataclass(slots=True)
class _Work:
    """Una nota en su paso por el pipeline."""

    item: DedupedArticle
    stored: StoredArticle
    text: ArticleText | None = None
    resolutions: list[Resolution] = field(default_factory=list)
    primary: Place | None = None
    result: EnrichmentResult | None = None
    # Consultas y buscadores que la trajeron (ADR-0114): el juez de un
    # concepto abierto los ve, para saber si una entidad que no está en el
    # título la encontró un buscador de texto completo.
    origins: tuple[QueryOrigin, ...] = ()


def _needs_body(w: _Work) -> bool:
    """Si una nota ya leída por la IA se vuelve a leer porque ahora sí hay de dónde.

    Google News RSS da links de Google que no se pueden descargar: la IA solo
    vio título y fragmento y, con «Hacker Eternal», marcó como no relevantes
    las 6 notas correctas (18/11/2026). Cuando Google web trae el link del
    medio de esa misma nota (``refresh_text``) y su texto fue de respaldo, se
    descarga el cuerpo y la IA la vuelve a juzgar (ADR-0115).

    Args:
        w: Nota en el pipeline.

    Returns:
        ``True`` si hay que leer su texto otra vez. Solo cuando se sabe que fue
        de respaldo: sin estado guardado no se vuelve a pagar a la IA.
    """
    return w.item.refresh_text and w.stored.extraction_status == ExtractionStatus.FALLBACK.value


def unconfirmed_matcher(concepts: Sequence[SearchConcept]) -> CoreMatcher | None:
    """Reconoce qué entidades de los conceptos abiertos no nombra una nota (ADR-0114).

    Args:
        concepts: Conceptos de la búsqueda.

    Returns:
        Un ``CoreMatcher`` con los términos obligatorios de los conceptos
        abiertos, o ``None`` si no tienen.
    """
    required = tuple(
        dict.fromkeys(
            term for c in concepts if c.query_mode is QueryMode.OPEN for term in c.required_terms
        )
    )
    return CoreMatcher(CoreTerms(required, ())) if required else None


def judge_hints(
    entities: CoreMatcher | None,
    title: str,
    snippet: str | None,
    notes: Sequence[tuple[str, str | None]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Qué entidades pedidas no nombra una nota y lo que se sabe de ellas (ADR-0114).

    Revisión del 18/11/2026 (hallazgo 4): con solo «el título no nombra a
    Eternal», el juez marcaba «por confirmar» cualquier nota del tema que
    trajo Google. Con lo que dicen de Eternal las notas de la misma búsqueda
    que sí lo nombran, solo lo es la que coincide con un hecho concreto.

    Args:
        entities: Entidades de los conceptos abiertos (``unconfirmed_matcher``);
            ``None`` si no hay.
        title: Título de la nota por juzgar.
        snippet: Su fragmento, si hay.
        notes: Título y fragmento de las notas de la búsqueda.

    Returns:
        ``(unconfirmed_terms, entity_context)`` para ``EnrichmentRequest``;
        los dos vacíos si la nota nombra todo o no hay entidades.
    """
    if entities is None:
        return (), ()
    missing = entities.missing_terms(title, snippet)
    return missing, entities.entity_context(notes, missing) if missing else ()


def web_section(article: RawArticle) -> str | None:
    """La sección de Google web de la que salió una nota, o ``None`` si no es de ahí.

    Args:
        article: Nota de un proveedor.

    Returns:
        Lo que el adaptador dejó en ``raw["section"]`` (``organic_results``,
        ``inline_videos``...). ``None`` en los demás proveedores.
    """
    if article.provider is not Provider.SEARCHAPI_WEB:
        return None
    section = article.raw.get(RAW_SECTION_KEY)
    return section if isinstance(section, str) else None


def origin_of(query: PlannedQuery, article: RawArticle | None = None) -> QueryOrigin:
    """La procedencia de una nota: con qué consulta y en qué buscador llegó (ADR-0114).

    Es de cada nota (revisión del 18/11/2026): Google web trae en la misma
    respuesta resultados orgánicos, que Google buscó en el texto completo, y
    carruseles (videos, tweets, noticias destacadas), que no.

    Args:
        query: Consulta ejecutada.
        article: La nota que trajo; sin ella, la procedencia de la consulta.

    Returns:
        Proveedor, su nombre en pantalla, las frases de la consulta, si buscó
        la nota en su texto completo (``FULL_TEXT_PROVIDERS`` y, en Google
        web, solo ``organic_results``) y la sección de Google web.
    """
    dialect = DIALECTS.get(query.provider)
    section = web_section(article) if article is not None else None
    full_text = query.provider in FULL_TEXT_PROVIDERS and (
        query.provider is not Provider.SEARCHAPI_WEB or section == WEB_ORGANIC_SECTION
    )
    return QueryOrigin(
        provider=query.provider.value,
        label=dialect.label if dialect is not None else query.provider.value,
        keywords=query.keywords,
        full_text=full_text,
        section=section,
    )


def _trace_origins(work: Sequence[_Work], execution: ExecutionResult) -> None:
    """Anota en cada nota las consultas que la trajeron, para el juez (ADR-0114).

    ``dedupe`` junta en una las copias de la misma nota (el link de Google
    News y el del medio) sin decir cuáles juntó. Se reconocen igual que ahí:
    por link canónico o por título normalizado. Un casi igual de título
    (similitud ≥ 0.9) que no coincide exacto pierde su procedencia; el juez
    ve entonces las de las demás copias.

    Args:
        work: Notas ya deduplicadas.
        execution: Lo que devolvió cada consulta.
    """
    if not any(o.query.core for o in execution.outcomes):
        return
    by_key: dict[str, dict[QueryOrigin, None]] = {}
    for outcome in execution.outcomes:
        for article in outcome.articles:
            origin = origin_of(outcome.query, article)
            for key in (canonical_url(article.url), normalize_name(article.title)):
                by_key.setdefault(key, {})[origin] = None
    for w in work:
        merged: dict[QueryOrigin, None] = {}
        for key in (w.item.url_canonical, w.item.title_norm):
            merged.update(by_key.get(key, {}))
        w.origins = tuple(merged)


@dataclass(slots=True)
class _Tally:
    """Conteos que se van llenando y se guardan como ``progress``."""

    stage: Stage = Stage.PLAN
    stages: dict[Stage, StageCount] = field(default_factory=dict)
    extra: dict[str, int] = field(default_factory=dict)
    usage: LLMUsage = NO_USAGE
    errors: list[str] = field(default_factory=list)
    # Títulos de muestra junto a un conteo de ``extra`` (``off_core_samples``).
    samples: dict[str, list[str]] = field(default_factory=dict)

    def as_json(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "stages": {
                s.value: {"total": c.total, "failed": c.failed} for s, c in self.stages.items()
            },
            **self.extra,
            **self.samples,
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
        classifier: ClassifyArticles | None = None,
        log_progress: Callable[[UUID, Mapping[str, object]], None] = lambda _id, _p: None,
        today: Today = mexico_city_today,
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
            classifier: Clasifica las notas por categoría (F12.4); sin él,
                no se clasifica.
            log_progress: Aviso de avance (el comando lo muestra en pantalla).
            today: Hoy en la Ciudad de México (las pruebas lo fijan): con él se
                sabe si una búsqueda manual era «últimos N días».
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
        self._classifier = classifier
        self._log_progress = log_progress
        self._today = today

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
        _trace_origins(work, execution)
        pending = await self._extract(search, tally, work)
        await self._enrich(search, tally, pending, work)
        work = self._drop_older_events(search, tally, work)
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
        # Una corrida automática tiene sus horas (time_window) y va por fechas
        # fijas; una manual que termina hoy era «últimos N días» (ADR-0113).
        window = (
            DateWindow.between(search.date_from, search.date_to)
            if search.time_window is not None
            else manual_window(search.date_from, search.date_to, self._today())
        )
        queries = plan_queries(search.concepts, place_for(facts), window, self._sources_of(search))
        return searched, queries

    async def _dedupe(
        self, search: StoredSearch, tally: _Tally, execution: ExecutionResult
    ) -> list[_Work]:
        await self._progress(search.search_id, tally, Stage.DEDUPE)
        found = self._on_topic(tally, self._on_core(tally, execution))
        window = strict_window(search)
        # Una nota sin fecha de Google web se queda en las búsquedas manuales:
        # Google ya filtró por fecha (ADR-0115). En las corridas, nunca.
        manual = search.time_window is None
        if window is not None:
            # Solo lo publicado en el periodo pedido. Corrida automática: desde
            # la corrida anterior (Benji, 28/10/2026). Búsqueda manual: los días
            # elegidos, de 00:00 a 23:59 de la Ciudad de México (11/11/2026:
            # «si le doy buscar hoy, solo hoy»). Lo de fuera ni se guarda ni se
            # paga a la IA.
            before = len(found)
            found = tuple(
                a
                for a in found
                if kept_by_window(window, a.published_at, (a.provider,), manual=manual)
            )
            tally.extra["outside_window"] = before - len(found)
        unique = dedupe(found, self._similarity)
        # Nivel 2 de duplicados (ADR-0025): la misma nota que ya se guardó en
        # otra búsqueda con otro link se reutiliza, con su IA ya pagada.
        candidates = await self._articles.known_like(unique)
        for item, known in zip(unique, candidates, strict=True):
            match = match_known(item, known, self._similarity)
            item.known_id = match.article_id if match else None
            # Si la guardada tenía el link de Google News y llegó el del medio,
            # su texto se vuelve a leer (ADR-0115, ver ``_needs_body``).
            item.refresh_text = match is not None and refreshes_link(item, match)
        stored = await self._articles.upsert(unique)
        work = [_Work(item, s) for item, s in zip(unique, stored, strict=True)]
        if window is not None:
            # Segundo filtro, con la fecha guardada: una nota vieja puede volver
            # con otra fecha (el índice local mandó en la corrida de las 15:00
            # del 28/10/2026 seis notas de la madrugada fechadas dentro de la
            # ventana). Ya guardada conserva su fecha real y era de la corrida
            # anterior: no le toca a esta.
            kept = [
                w
                for w in work
                if kept_by_window(
                    window,
                    w.stored.published_at or w.item.article.published_at,
                    (s.provider for s in w.item.sightings),
                    manual=manual,
                )
            ]
            tally.extra["outside_window"] += len(work) - len(kept)
            work = kept
        tally.extra["articles"] = len(work)
        tally.extra["known"] = sum(1 for w in work if w.item.known_id is not None)
        return work

    @staticmethod
    def _on_topic(tally: _Tally, execution: ExecutionResult) -> tuple[RawArticle, ...]:
        """Quita lo que trajo una consulta con subdivisión sin la palabra del tema arriba.

        Benji, 03/11/2026 (ADR-0038): en «FGR · Homicidio» la palabra de la
        subdivisión debe estar en el título o el resumen, no perdida en el
        cuerpo; los buscadores la encuentran en todo el artículo. Lo que no
        cumple ni se guarda ni se paga a la IA. Una nota que también trajo
        otra consulta sin subdivisión se queda por esa otra.

        Args:
            tally: Conteos (suma ``off_topic`` si hubo subdivisión).
            execution: Lo que devolvió cada consulta.

        Returns:
            Las notas que cumplen, sin deduplicar todavía.
        """
        if not any(o.query.topic_terms for o in execution.outcomes):
            return execution.articles
        kept: list[RawArticle] = []
        for outcome in execution.outcomes:
            matcher = TopicMatcher(outcome.query.topic_terms)
            kept.extend(a for a in outcome.articles if matcher.found_in(a.title, a.snippet))
        tally.extra["off_topic"] = len(execution.articles) - len(kept)
        return tuple(kept)

    @staticmethod
    def _on_core(tally: _Tally, execution: ExecutionResult) -> ExecutionResult:
        """Quita lo que no nombra lo pedido en un concepto abierto (ADR-0114).

        Benji, 18/11/2026: «las relevantes deben hablar de verdad de lo
        pedido y las no relevantes no deben ser basura total». Cada nota se
        revisa con el ``CoreTerms`` de la consulta que la trajo y con su propia
        procedencia (``origin_of``): lo que trajo Google con texto completo
        solo necesita la entidad (con la excepción por procedencia); un
        carrusel de Google web, la entidad en el título, el fragmento o el
        canal; lo demás, la entidad y alguna raíz del tema. Lo que no cumple
        ni se guarda ni se paga a la IA. Una nota que también trajo una
        consulta de un concepto exacto se queda por esa otra.

        Va justo antes de ``_on_topic`` porque necesita saber qué consulta
        trajo cada nota, y ``_on_topic`` ya las devuelve todas juntas. El
        resultado es el mismo en cualquier orden (los dos miran cada nota con
        su consulta); solo cambia qué contador suma una nota que falla los dos.

        Args:
            tally: Conteos: ``off_core`` (notas distintas que no quedaron por
                ninguna consulta) y ``off_core_samples`` (hasta
                ``OFF_CORE_SAMPLES`` títulos), si hubo conceptos abiertos.
            execution: Lo que devolvió cada consulta.

        Returns:
            Lo mismo, sin las notas que no pasan.
        """
        if not any(o.query.core for o in execution.outcomes):
            return execution
        outcomes: list[QueryOutcome] = []
        dropped: dict[str, str] = {}
        for outcome in execution.outcomes:
            core = outcome.query.core
            if core is None:
                outcomes.append(outcome)
                continue
            matcher = CoreMatcher(core)
            kept = []
            for a in outcome.articles:
                # La procedencia es de cada nota: en Google web, un video no
                # cuenta como texto completo y un orgánico sí.
                origin = origin_of(outcome.query, a)
                if matcher.check(a.title, a.snippet, origin, a.source_name).kept:
                    kept.append(a)
                else:
                    dropped.setdefault(canonical_url(a.url), a.title)
            outcomes.append(replace(outcome, articles=tuple(kept)))
        filtered = ExecutionResult(tuple(outcomes))
        # Una nota descartada en una consulta pero traída por otra sigue en la
        # búsqueda: no cuenta como descartada.
        survivors = {canonical_url(a.url) for a in filtered.articles} | {
            normalize_name(a.title) for a in filtered.articles
        }
        lost = [
            t
            for u, t in dropped.items()
            if u not in survivors and normalize_name(t) not in survivors
        ]
        tally.extra["off_core"] = len(lost)
        tally.samples["off_core_samples"] = list(dict.fromkeys(lost))[:OFF_CORE_SAMPLES]
        return filtered

    @staticmethod
    def _drop_older_events(search: StoredSearch, tally: _Tally, work: list[_Work]) -> list[_Work]:
        """En una corrida, quita las notas cuyo hecho es de antes de su periodo.

        Benji, 28/10/2026: «no quiero que al ver una corrida me salgan noticias
        de otros días». La IA dice la fecha de lo que informa la nota
        (``enrich_v3``): la sentencia que se dictó hoy entra aunque el delito
        sea de 2019; el cateo de ayer, publicado hoy, no. Se compara por día
        en la Ciudad de México: la fecha del hecho no trae hora. Sin fecha
        (la IA no la supo o no leyó la nota), la nota se queda.

        Args:
            search: La búsqueda; solo filtra si es una corrida con ventana.
            tally: Conteos (suma ``older_event``).
            work: Notas ya leídas por la IA.

        Returns:
            Las notas que le tocan a la corrida.
        """
        window = strict_window(search)
        if window is None:
            return work
        first_day = window.start.astimezone(MEXICO_CITY).date()

        def event_date(w: _Work) -> date | None:
            if w.result is not None:
                return w.result.enrichment.event_date
            return w.stored.event_date

        kept = [w for w in work if (day := event_date(w)) is None or day >= first_day]
        tally.extra["older_event"] = len(work) - len(kept)
        return kept

    async def _extract(self, search: StoredSearch, tally: _Tally, work: list[_Work]) -> list[_Work]:
        """Lee el texto de las notas que hay que enriquecer (respetando el tope)."""
        concept_ids = frozenset(c.concept_id for c in search.concepts)
        version = self._llm.prompt_version
        fresh = [
            w for w in work if not w.stored.reusable_for(version, concept_ids) or _needs_body(w)
        ]
        tally.extra["reused"] = len(work) - len(fresh)
        # Con el tope de la IA, primero las que nombran lo pedido en el título
        # o el fragmento (revisión del 18/11/2026): una «por confirmar» no le
        # quita el lugar a una que sí lo nombra. El orden es estable.
        entities = unconfirmed_matcher(search.concepts)
        if entities is not None:
            fresh.sort(
                key=lambda w: bool(
                    entities.missing_terms(w.item.article.title, w.item.article.snippet)
                )
            )
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

    async def _enrich(
        self, search: StoredSearch, tally: _Tally, pending: list[_Work], work: Sequence[_Work]
    ) -> None:
        """Pasa por la IA las notas pendientes.

        Args:
            search: La búsqueda.
            tally: Conteos.
            pending: Notas que se le mandan a la IA (ya con texto).
            work: Todas las notas de la búsqueda: de las que nombran la
                entidad sale lo que se sabe de ella (``judge_hints``).
        """
        await self._progress(search.search_id, tally, Stage.ENRICH)
        briefs = [
            ConceptBrief(
                c.concept_id, c.name, c.description, c.keywords, c.query_mode, c.required_terms
            )
            for c in search.concepts
        ]
        # ADR-0114: el juez de un concepto abierto sabe dónde se busca, cómo
        # llegó cada nota y qué entidad no está en su título.
        searched = await self._gazetteer.by_code(search.region_code)
        region = searched.display_name if searched is not None else None
        entities = unconfirmed_matcher(search.concepts)
        notes = [(w.item.article.title, w.item.article.snippet) for w in work]
        semaphore = asyncio.Semaphore(self._limits.llm_concurrency)
        failures: list[str] = []
        done = 0

        async def one(w: _Work, text: ArticleText) -> None:
            nonlocal done
            article = w.item.article
            unconfirmed, context = judge_hints(entities, article.title, article.snippet, notes)
            request = EnrichmentRequest(
                article.title,
                text_for_llm(text.text.text),
                article.published_at,
                briefs,
                region=region,
                origins=w.origins[:MAX_PROMPT_ORIGINS],
                unconfirmed_terms=unconfirmed,
                entity_context=context,
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

    async def _classify(self, search: StoredSearch, tally: _Tally, work: list[_Work]) -> None:
        """Clasifica por categoría las notas encontradas (F12.4, ADR-0029).

        Va al cierre porque usa el resumen de la IA. Su costo se suma al de
        la búsqueda. Si falla, la búsqueda sigue con su estado y el error queda
        en ``processing_errors``: las notas se clasifican en otra pasada.
        """
        if self._classifier is None or not work:
            return
        try:
            report = await self._classifier.run([w.stored.article_id for w in work])
        except ClassificationError as error:
            tally.usage += error.usage
            await self._record_close_error(search, error, f"Clasificación: {error}")
            return
        except Exception as error:
            await self._record_close_error(search, error, f"Clasificación: {error}")
            return
        tally.usage += report.usage
        tally.extra["classified"] = report.classified

    async def _record_close_error(
        self, search: StoredSearch, error: Exception, message: str
    ) -> None:
        await self._searches.record_error(
            ProcessingErrorRecord(search.search_id, Stage.CLOSE, type(error).__name__, message)
        )

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
            inside = (
                in_region(w.primary, searched, w.item.article.source_domain)
                if searched is not None
                else None
            )
            located[inside] += 1
            rows.extend(
                SearchResultRow(w.stored.article_id, s.provider, s.rank, inside)
                for s in w.item.sightings
            )
        if rows:
            await self._articles.link_results(search.search_id, rows)
        await self._classify(search, tally, work)
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
