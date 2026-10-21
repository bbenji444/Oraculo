"""Volver a ubicar las notas de una búsqueda sin llamar a la IA (§11).

Cuando cambian las reglas del geolocalizador o el catálogo (por ejemplo,
alias nuevos), las menciones de lugar ya guardadas se resuelven de nuevo
contra el catálogo y se recalcula ``in_region``. No cuesta nada: la IA no
participa.

No hace: no vuelve a extraer el texto ni a resumir.
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from app.application.audit import Actor
from app.application.ports.geocoding import GazetteerPort
from app.application.ports.llm import EnrichmentError, EnrichmentRequest, LLMPort
from app.application.ports.search_store import (
    ProcessingErrorRecord,
    RelocationStorePort,
    ReprocessStorePort,
    SearchStorePort,
    StoredText,
)
from app.application.use_cases.geocoding import GeocodeMentions, search_area
from app.application.use_cases.run_search import NO_USAGE, PipelineLimits, SearchNotFoundError
from app.domain.enrichment import ConceptBrief, LLMUsage, text_for_llm
from app.domain.errors import NotFoundError, ProviderError
from app.domain.geocoding import Place
from app.domain.search import Stage, in_region


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
            inside = in_region(after, searched)
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


@dataclass(frozen=True, slots=True)
class ReprocessReport:
    """Resultado de volver a pasar las notas por la IA.

    Attributes:
        relocations: Antes y después de cada nota reprocesada.
        failed: Notas en las que la IA falló (conservan lo anterior).
        usage: Tokens gastados.
        cost_usd: Costo estimado.
    """

    relocations: tuple[Relocation, ...]
    failed: int
    usage: LLMUsage
    cost_usd: float


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

    async def run(self, search_id: UUID) -> ReprocessReport:
        """Reprocesa las notas que conservan su texto.

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
        searched = searched and await search_area(self._gazetteer, searched)
        if searched is None:
            raise NotFoundError(f"No existe la región {search.region_code} en el catálogo.")
        briefs = [
            ConceptBrief(c.concept_id, c.name, c.description, c.keywords) for c in search.concepts
        ]
        before = {
            m.article_id: m.primary_code for m in await self._store.search_mentions(search_id)
        }
        semaphore = asyncio.Semaphore(self._limits.llm_concurrency)
        usage = NO_USAGE
        failed = 0

        async def one(item: StoredText) -> Relocation | None:
            nonlocal usage, failed
            request = EnrichmentRequest(
                item.title, text_for_llm(item.text), item.published_at, briefs
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
            inside = in_region(after, searched)
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
        return ReprocessReport(tuple(done), failed, usage, cost)
