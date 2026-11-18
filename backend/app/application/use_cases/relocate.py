"""Volver a ubicar las notas de una búsqueda sin llamar a la IA (§11).

Cuando cambian las reglas del geolocalizador o el catálogo (por ejemplo,
alias nuevos), las menciones de lugar ya guardadas se resuelven de nuevo
contra el catálogo y se recalcula ``in_region``. No cuesta nada: la IA no
participa.

``ReprocessSearch`` (``make reubicar --con-ia``) sí vuelve a pasar el texto
guardado por la IA. En los conceptos abiertos rearma lo que el juez vio en
vivo (ADR-0114): de dónde llegó cada nota (``rebuilt_origins``), qué
entidad no nombra su título y lo que se sabe de ella por otras notas. Lo que
no se guarda (qué consulta trajo cada nota, la sección de Google web) se
avisa antes de gastar (``ReprocessSearch.warnings``).

No hace: no vuelve a extraer el texto ni a resumir.
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.application.audit import Actor
from app.application.ports.geocoding import GazetteerPort
from app.application.ports.llm import EnrichmentError, EnrichmentRequest, LLMPort
from app.application.ports.search_store import (
    ProcessingErrorRecord,
    RelocationStorePort,
    ReprocessStorePort,
    SearchConcept,
    SearchProvenance,
    SearchStorePort,
    StoredOrigin,
    StoredText,
)
from app.application.use_cases.geocoding import GeocodeMentions, search_area
from app.application.use_cases.run_search import (
    MAX_PROMPT_ORIGINS,
    NO_USAGE,
    PipelineLimits,
    SearchNotFoundError,
    judge_hints,
    unconfirmed_matcher,
)
from app.domain.concept import QueryMode
from app.domain.core_terms import CoreMatcher, QueryOrigin
from app.domain.enrichment import ConceptBrief, LLMUsage, text_for_llm
from app.domain.errors import NotFoundError, ProviderError
from app.domain.geocoding import Place
from app.domain.queries import FULL_TEXT_PROVIDERS, Provider
from app.domain.query_dialects import DIALECTS
from app.domain.search import Stage, in_region

# Avisos de ``make reubicar --con-ia`` en una búsqueda con conceptos abiertos
# (revisión del 18/11/2026, hallazgo 5): qué no se puede rearmar de lo que el
# juez vio en vivo, para no sacar conclusiones de un juicio distinto.
REBUILT_PROVENANCE_WARNING = (
    "La procedencia se rearma con lo guardado: qué proveedores trajeron cada nota y el "
    "texto de las consultas de esa búsqueda. No se guarda cuál consulta trajo cada nota."
)
WEB_SECTION_WARNING = (
    "Google web no guarda de qué sección salió cada nota (resultado orgánico o carrusel): "
    "al volver a juzgar no cuenta como buscador de texto completo, y sus notas sin la "
    "entidad en el título quedan, a lo más, cercanas."
)
NO_ENTITY_WARNING = (
    "Los conceptos abiertos de esta búsqueda no tienen entidad obligatoria guardada "
    "(búsquedas de antes de la migración 0049): la regla de procedencia no aplica."
)
NO_QUERIES_WARNING = (
    "No hay consultas guardadas de esta búsqueda (provider_queries): la regla de "
    "procedencia no aplica."
)


@dataclass(frozen=True, slots=True)
class Relocation:
    """Cómo cambió la ubicación principal de una nota.

    Attributes:
        article_id: Nota.
        title: Título.
        before: Ubicación principal anterior.
        after: Ubicación principal nueva.
        in_region: Si ahora cae en la región buscada.
    """

    article_id: int
    title: str
    before: Place | None
    after: Place | None
    in_region: bool | None

    @property
    def changed(self) -> bool:
        """``True`` si cambió la ubicación principal."""
        return self.before != self.after


class RelocateSearch:
    """Resuelve otra vez las menciones guardadas de una búsqueda."""

    def __init__(
        self,
        searches: SearchStorePort,
        store: RelocationStorePort,
        gazetteer: GazetteerPort,
        geocoder: GeocodeMentions,
    ) -> None:
        """Recibe las piezas.

        Args:
            searches: Búsquedas (para la región buscada).
            store: Menciones y ubicaciones guardadas.
            gazetteer: Catálogo.
            geocoder: Geolocalizador con las reglas vigentes.
        """
        self._searches = searches
        self._store = store
        self._gazetteer = gazetteer
        self._geocoder = geocoder

    async def run(self, search_id: UUID) -> list[Relocation]:
        """Vuelve a ubicar todas las notas de la búsqueda.

        Args:
            search_id: Búsqueda.

        Returns:
            Una entrada por nota, con su antes y después.

        Raises:
            SearchNotFoundError: Si la búsqueda no existe.
            NotFoundError: Si su región ya no está en el catálogo.
        """
        search = await self._searches.load(search_id)
        if search is None:
            raise SearchNotFoundError(f"No existe la búsqueda {search_id}.")
        searched = await self._gazetteer.by_code(search.region_code)
        searched = searched and await search_area(self._gazetteer, searched)
        if searched is None:
            raise NotFoundError(f"No existe la región {search.region_code} en el catálogo.")
        relocations = []
        for item in await self._store.search_mentions(search_id):
            before = await self._gazetteer.by_code(item.primary_code) if item.primary_code else None
            after = before
            if item.mentions:
                resolutions = await self._geocoder.run(item.mentions, searched)
                await self._store.save_locations(item.article_id, resolutions)
                after = next((r.place for r in resolutions if r.is_primary), None)
            inside = in_region(after, searched, item.source_domain)
            await self._store.set_in_region(search_id, item.article_id, inside)
            relocations.append(Relocation(item.article_id, item.title, before, after, inside))
        await self._store.merge_progress(
            search_id,
            {
                "in_region": sum(1 for r in relocations if r.in_region is True),
                "out_of_region": sum(1 for r in relocations if r.in_region is False),
                "unlocated": sum(1 for r in relocations if r.in_region is None),
            },
        )
        return relocations


def rebuilt_origins(
    note: StoredOrigin, query_texts: Mapping[str, Sequence[str]], entities: CoreMatcher | None
) -> tuple[QueryOrigin, ...]:
    """La procedencia de una nota rearmada con lo guardado (revisión del 18/11/2026).

    En vivo (``origin_of``) se sabe qué consulta trajo cada nota; guardado,
    solo qué proveedores la trajeron y qué consultas se le mandaron a cada
    uno. De esas cuentan las que nombran una entidad pedida («hacker
    eternal»): son las que pudieron traerla por procedencia. Google web no
    guarda la sección de la nota y no cuenta como texto completo: si dudas,
    no es relevante.

    Args:
        note: La nota con sus proveedores.
        query_texts: Texto de las consultas de la búsqueda, por proveedor.
        entities: Entidades de los conceptos abiertos (``unconfirmed_matcher``).

    Returns:
        Una procedencia por proveedor conocido que tenga consultas guardadas,
        con las consultas que nombran la entidad o, si ninguna la nombra, la
        primera.
    """
    origins: list[QueryOrigin] = []
    for name in note.providers:
        try:
            provider = Provider(name)
        except ValueError:
            # Un proveedor que ya no existe no dice nada de cómo buscó.
            continue
        sent = tuple(query_texts.get(name, ()))
        if not sent:
            continue
        carrying = tuple(
            t
            for t in sent
            if entities is not None
            and len(entities.missing_terms(t, None)) < len(entities.required)
        )
        dialect = DIALECTS.get(provider)
        origins.append(
            QueryOrigin(
                provider=name,
                label=dialect.label if dialect is not None else name,
                keywords=carrying or sent[:1],
                full_text=(
                    provider in FULL_TEXT_PROVIDERS and provider is not Provider.SEARCHAPI_WEB
                ),
            )
        )
    return tuple(origins)


def provenance_warnings(
    concepts: Sequence[SearchConcept], provenance: SearchProvenance
) -> tuple[str, ...]:
    """Lo que no se puede rearmar del juicio en vivo de los conceptos abiertos.

    Args:
        concepts: Conceptos de la búsqueda.
        provenance: Lo que quedó guardado de cómo llegaron sus notas.

    Returns:
        Los avisos para el comando, en orden; vacío si no hay conceptos
        abiertos (la FGR y los temas no usan procedencia).
    """
    open_concepts = [c for c in concepts if c.query_mode is QueryMode.OPEN]
    if not open_concepts:
        return ()
    warnings = [REBUILT_PROVENANCE_WARNING]
    if not any(c.required_terms for c in open_concepts):
        warnings.append(NO_ENTITY_WARNING)
    elif not provenance.query_texts:
        warnings.append(NO_QUERIES_WARNING)
    if any(Provider.SEARCHAPI_WEB.value in n.providers for n in provenance.notes):
        warnings.append(WEB_SECTION_WARNING)
    return tuple(warnings)


@dataclass(frozen=True, slots=True)
class ReprocessReport:
    """Resultado de volver a pasar las notas por la IA.

    Attributes:
        relocations: Antes y después de cada nota reprocesada.
        failed: Notas en las que la IA falló (conservan lo anterior).
        usage: Tokens gastados.
        cost_usd: Costo estimado.
        warnings: Lo que no se pudo rearmar de la procedencia
            (``provenance_warnings``).
    """

    relocations: tuple[Relocation, ...]
    failed: int
    usage: LLMUsage
    cost_usd: float
    warnings: tuple[str, ...] = ()


class ReprocessSearch:
    """Vuelve a pasar por la IA el texto guardado de las notas de una búsqueda.

    Sirve cuando cambia el prompt o hacen falta datos que antes no se
    guardaban (las pistas de lugar, migración 0014). No consulta proveedores
    ni vuelve a bajar páginas: usa ``article_texts``.
    """

    def __init__(  # noqa: PLR0913 — una pieza por paso, todo por nombre (*)
        self,
        *,
        searches: SearchStorePort,
        store: ReprocessStorePort,
        gazetteer: GazetteerPort,
        geocoder: GeocodeMentions,
        llm: LLMPort,
        limits: PipelineLimits,
    ) -> None:
        """Recibe las piezas.

        Args:
            searches: Búsquedas.
            store: Textos, enriquecimiento y ubicaciones guardados.
            gazetteer: Catálogo.
            geocoder: Geolocalizador.
            llm: La IA.
            limits: Concurrencia y precios de la IA.
        """
        self._searches = searches
        self._store = store
        self._gazetteer = gazetteer
        self._geocoder = geocoder
        self._llm = llm
        self._limits = limits

    async def _provenance(
        self, concepts: Sequence[SearchConcept], search_id: UUID
    ) -> SearchProvenance:
        """Lo guardado de cómo llegaron las notas; solo se lee si hay conceptos abiertos."""
        if not any(c.query_mode is QueryMode.OPEN for c in concepts):
            return SearchProvenance((), {})
        return await self._store.search_provenance(search_id)

    async def warnings(self, search_id: UUID) -> tuple[str, ...]:
        """Lo que no se podrá rearmar de la procedencia, para avisar antes de gastar.

        Args:
            search_id: Búsqueda.

        Returns:
            Los avisos de ``provenance_warnings``.

        Raises:
            SearchNotFoundError: Si la búsqueda no existe.
        """
        search = await self._searches.load(search_id)
        if search is None:
            raise SearchNotFoundError(f"No existe la búsqueda {search_id}.")
        provenance = await self._provenance(search.concepts, search_id)
        return provenance_warnings(search.concepts, provenance)

    async def run(self, search_id: UUID) -> ReprocessReport:
        """Reprocesa las notas que conservan su texto.

        En los conceptos abiertos el juez recibe, como en vivo, la
        procedencia rearmada (``rebuilt_origins``), las entidades que el
        título no nombra y lo que se sabe de ellas (``judge_hints``).

        Args:
            search_id: Búsqueda.

        Returns:
            Antes y después, fallas y costo.

        Raises:
            SearchNotFoundError: Si la búsqueda no existe.
            NotFoundError: Si su región ya no está en el catálogo.
        """
        search = await self._searches.load(search_id)
        if search is None:
            raise SearchNotFoundError(f"No existe la búsqueda {search_id}.")
        searched = await self._gazetteer.by_code(search.region_code)
        # El juez de un concepto abierto sabe dónde se busca (ADR-0114).
        region = searched.display_name if searched is not None else None
        searched = searched and await search_area(self._gazetteer, searched)
        if searched is None:
            raise NotFoundError(f"No existe la región {search.region_code} en el catálogo.")
        briefs = [
            ConceptBrief(
                c.concept_id, c.name, c.description, c.keywords, c.query_mode, c.required_terms
            )
            for c in search.concepts
        ]
        before = {
            m.article_id: m.primary_code for m in await self._store.search_mentions(search_id)
        }
        provenance = await self._provenance(search.concepts, search_id)
        entities = unconfirmed_matcher(search.concepts)
        stored = {n.article_id: n for n in provenance.notes}
        notes = [(n.title, n.snippet) for n in provenance.notes]
        semaphore = asyncio.Semaphore(self._limits.llm_concurrency)
        usage = NO_USAGE
        failed = 0

        async def one(item: StoredText) -> Relocation | None:
            nonlocal usage, failed
            note = stored.get(item.article_id)
            snippet = note.snippet if note is not None else None
            origins = rebuilt_origins(note, provenance.query_texts, entities) if note else ()
            unconfirmed, context = judge_hints(entities, item.title, snippet, notes)
            request = EnrichmentRequest(
                item.title,
                text_for_llm(item.text),
                item.published_at,
                briefs,
                region=region,
                origins=origins[:MAX_PROMPT_ORIGINS],
                unconfirmed_terms=unconfirmed,
                entity_context=context,
            )
            try:
                async with semaphore:
                    result = await self._llm.enrich(request)
            except (EnrichmentError, ProviderError) as error:
                if isinstance(error, EnrichmentError):
                    usage += error.usage
                failed += 1
                message = error.message if isinstance(error, ProviderError) else str(error)
                await self._searches.record_error(
                    ProcessingErrorRecord(
                        search_id, Stage.ENRICH, type(error).__name__, message, item.article_id
                    )
                )
                return None
            usage += result.usage
            resolutions = await self._geocoder.run(result.enrichment.locations, searched)
            await self._store.save_enrichment(item.article_id, result, resolutions)
            after = next((r.place for r in resolutions if r.is_primary), None)
            inside = in_region(after, searched, item.source_domain)
            await self._store.set_in_region(search_id, item.article_id, inside)
            code = before.get(item.article_id)
            old = await self._gazetteer.by_code(code) if code else None
            return Relocation(item.article_id, item.title, old, after, inside)

        texts = await self._store.search_texts(search_id)
        done = [r for r in await asyncio.gather(*(one(t) for t in texts)) if r is not None]
        cost = usage.cost_usd(
            self._limits.price_input_per_million, self._limits.price_output_per_million
        )
        await self._store.add_llm_usage(search_id, usage, cost, Actor(search.user_id))
        await RelocateSearch(self._searches, self._store, self._gazetteer, self._geocoder).run(
            search_id
        )
        warnings = provenance_warnings(search.concepts, provenance)
        return ReprocessReport(tuple(done), failed, usage, cost, warnings)
