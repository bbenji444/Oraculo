"""Puerto de lectura de búsquedas para la API (especificación §13).

Separa lo que la pantalla lee (detalle, historial, notas y conteos) de lo
que el pipeline escribe (``search_store``). La implementación está en
``app/adapters/persistence/search_repository.py``.

No hace: no decide nada ni escribe.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.application.pagination import TimeCursor
from app.domain.aggregates import NoteLocation
from app.domain.enrichment import LLMUsage
from app.domain.search import SearchStatus


@dataclass(frozen=True, slots=True)
class ConceptRef:
    """Un concepto tal como se usó en la búsqueda.

    Attributes:
        id: Id del concepto.
        name: Nombre al momento de buscar.
    """

    id: int
    name: str


@dataclass(frozen=True, slots=True)
class SearchDetail:
    """Una búsqueda con su estado, avance y costo.

    Attributes:
        search_id: Id.
        user_id: Quién la pidió.
        status: Estado.
        region_id: Región buscada.
        region_code: Su clave (INEGI o ISO-A3).
        region_name: Su nombre.
        date_from: Primer día.
        date_to: Último día.
        concepts: Conceptos de la búsqueda.
        progress: Etapa actual y conteos (``RunSearch``).
        queries_planned: Consultas planeadas.
        credits_estimated: Créditos estimados.
        credits_used: Créditos gastados.
        llm_usage: Tokens de la IA.
        llm_cost_usd: Costo estimado de la IA.
        results_count: Notas distintas encontradas.
        error_summary: Qué falló, si algo falló.
        created_at: Cuándo se pidió (UTC).
        started_at: Cuándo empezó a correr.
        finished_at: Cuándo terminó.
    """

    search_id: UUID
    user_id: str
    status: SearchStatus
    region_id: int
    region_code: str
    region_name: str
    date_from: date
    date_to: date
    concepts: tuple[ConceptRef, ...]
    progress: Mapping[str, object]
    queries_planned: int
    credits_estimated: int
    credits_used: int
    llm_usage: LLMUsage
    llm_cost_usd: float
    results_count: int
    error_summary: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SearchReaderPort(Protocol):
    """Lecturas de búsquedas para la API."""

    async def search_detail(self, search_id: UUID) -> SearchDetail | None:
        """Una búsqueda.

        Args:
            search_id: Id.

        Returns:
            La búsqueda, o ``None`` si no existe.
        """
        ...

    async def history(
        self, user_id: str, after: TimeCursor | None, limit: int
    ) -> list[SearchDetail]:
        """Búsquedas de una persona, de la más reciente a la más vieja.

        Args:
            user_id: Quién las pidió.
            after: Cursor de la página anterior.
            limit: Cuántas como máximo.

        Returns:
            Las búsquedas de la página.
        """
        ...


class InRegion(StrEnum):
    """Filtro de las notas por región (las tres listas de la pantalla)."""

    INSIDE = "true"
    OUTSIDE = "false"
    UNLOCATED = "none"


@dataclass(frozen=True, slots=True)
class ArticleFilters:
    """Qué notas de una búsqueda se quieren.

    Attributes:
        relevant_only: Solo las relevantes para algún concepto (por defecto).
        in_region: Dentro, fuera o sin ubicación; ``None`` = todas.
        precisions: Precisión de la ubicación principal (``unknown`` = sin
            ubicación); vacío = todas.
        concept_id: Solo las de este concepto (relevantes, salvo que
            ``relevant_only`` sea ``False``).
    """

    relevant_only: bool = True
    in_region: InRegion | None = None
    precisions: frozenset[str] = frozenset()
    concept_id: int | None = None


@dataclass(frozen=True, slots=True)
class JudgementView:
    """Lo que dijo la IA de una nota para un concepto.

    Attributes:
        concept_id: Concepto.
        name: Su nombre.
        is_relevant: Si es relevante.
        relevance_score: De 0 a 1.
        relevance_reason: Por qué.
    """

    concept_id: int
    name: str
    is_relevant: bool
    relevance_score: float
    relevance_reason: str | None


@dataclass(frozen=True, slots=True)
class LocationView:
    """Una mención de lugar resuelta contra el catálogo.

    Attributes:
        mention: Texto de la mención.
        role: ``event`` (donde pasó) o ``mentioned``.
        precision: ``country``, ``state``, ``municipality``, ``locality`` o
            ``unknown``.
        confidence: De 0 a 1.
        is_primary: Si es la ubicación principal (la que se pinta).
        region_id: Región del catálogo, si se resolvió.
        region_code: Su clave.
        place: Nombre para mostrar ("Alcaldía Iztapalapa").
        lon: Longitud del punto del catálogo.
        lat: Latitud.
    """

    mention: str
    role: str
    precision: str
    confidence: float
    is_primary: bool
    region_id: int | None
    region_code: str | None
    place: str | None
    lon: float | None
    lat: float | None


@dataclass(frozen=True, slots=True)
class ArticleItem:
    """Una nota en la lista de resultados.

    Attributes:
        article_id: Id.
        title: Título.
        source_name: Medio.
        source_domain: Dominio del medio.
        url: Link a la nota (nunca se guarda el texto completo, §8).
        published_at: Fecha de publicación.
        summary: Resumen propio de la IA.
        event_type: Tipo de hecho.
        event_date: Fecha del hecho.
        extraction_status: ``ok`` o ``fallback`` (solo título y fragmento).
        enrichment_status: ``ok``, ``pending``, ``failed``.
        judgements: Juicio de la IA por concepto de la búsqueda.
        primary: Ubicación principal, si tiene.
        in_region: Si cae en la región buscada (``None``: sin ubicación).
        providers: Quién la encontró en esta búsqueda.
    """

    article_id: int
    title: str
    source_name: str | None
    source_domain: str | None
    url: str
    published_at: datetime | None
    summary: str | None
    event_type: str | None
    event_date: date | None
    extraction_status: str
    enrichment_status: str
    judgements: tuple[JudgementView, ...]
    primary: LocationView | None
    in_region: bool | None
    providers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArticleDetail:
    """Una nota con todo lo que se sabe de ella (nunca el texto completo).

    Attributes:
        item: Lo mismo que en la lista (los conceptos, de todas sus búsquedas).
        locations: Todas sus menciones de lugar.
        first_seen_at: Cuándo la vio el sistema por primera vez.
        llm_model: Modelo que la resumió.
        prompt_version: Versión del prompt.
    """

    item: ArticleItem
    locations: tuple[LocationView, ...]
    first_seen_at: datetime
    llm_model: str | None
    prompt_version: str | None


@dataclass(frozen=True, slots=True)
class RegionPoint:
    """Una región para el mapa: nombre y centro.

    Attributes:
        region_id: Id.
        code: Clave (INEGI o ISO-A3).
        name: Nombre.
        lon: Longitud del centro.
        lat: Latitud del centro.
    """

    region_id: int
    code: str
    name: str
    lon: float
    lat: float


class ArticleReaderPort(Protocol):
    """Lecturas de notas para la API."""

    async def search_articles(
        self, search_id: UUID, filters: ArticleFilters, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        """Notas de una búsqueda, de la más reciente a la más vieja (sin fecha al final).

        Args:
            search_id: Búsqueda.
            filters: Filtros.
            after: Cursor de la página anterior.
            limit: Cuántas como máximo.

        Returns:
            Las notas de la página.
        """
        ...

    async def article_detail(self, article_id: int) -> ArticleDetail | None:
        """Una nota.

        Args:
            article_id: Id.

        Returns:
            La nota, o ``None`` si no existe.
        """
        ...

    async def note_locations(self, search_id: UUID, filters: ArticleFilters) -> list[NoteLocation]:
        """Ubicación principal de cada nota de una búsqueda (para el mapa de calor).

        Args:
            search_id: Búsqueda.
            filters: Filtros (los mismos de la lista de notas).

        Returns:
            Una por nota.
        """
        ...

    async def regions_by_code(self, codes: Sequence[str]) -> list[RegionPoint]:
        """Nombre y centro de varias regiones.

        Args:
            codes: Claves (INEGI o ISO-A3).

        Returns:
            Las que existen, en cualquier orden.
        """
        ...
