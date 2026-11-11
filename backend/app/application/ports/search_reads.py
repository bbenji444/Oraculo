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
from app.domain.authority import Authority
from app.domain.enrichment import LLMUsage
from app.domain.search import SearchStatus, SearchTrigger


@dataclass(frozen=True, slots=True)
class ConceptRef:
    """Un concepto tal como se usó en la búsqueda.

    Attributes:
        id: Id del concepto.
        name: Nombre al momento de buscar.
        subdivision_ids: Subdivisiones con que se buscó («FGR + Homicidio»).
    """

    id: int
    name: str
    subdivision_ids: tuple[int, ...] = ()


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
        providers: Fuentes con las que se hizo (ADR-0027); vacío en las de
            antes de F12.2, que usaron todas las configuradas.
        trigger: Quién la lanzó (F12.8): una persona o el reloj.
        scheduled_for: Hora programada de una corrida automática.
        window_start: Inicio de las horas que cubre una corrida automática.
        window_end: Fin de esas horas (la hora de la corrida).
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
    providers: tuple[str, ...] = ()
    trigger: SearchTrigger = SearchTrigger.MANUAL
    scheduled_for: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


@dataclass(frozen=True, slots=True)
class SearchOwnership:
    """De quién es una búsqueda, para decidir si se puede eliminar.

    Attributes:
        user_id: Quién la lanzó.
        trigger: Manual o automática.
        deleted: Si ya está eliminada.
    """

    user_id: str
    trigger: SearchTrigger
    deleted: bool


class SearchTrashPort(Protocol):
    """Quitar búsquedas del historial sin perderlas (reversible)."""

    async def ownership(self, search_id: UUID) -> SearchOwnership | None:
        """De quién es la búsqueda, aunque esté eliminada.

        Args:
            search_id: Id.

        Returns:
            Dueño, origen y si está eliminada; ``None`` si no existe.
        """
        ...

    async def set_deleted(
        self, search_id: UUID, *, deleted: bool, actor_id: str, ip: str | None, action: str
    ) -> None:
        """Elimina o restaura la búsqueda y deja la bitácora en la misma transacción.

        Args:
            search_id: Id.
            deleted: ``True`` para eliminar, ``False`` para restaurar.
            actor_id: Quién lo hace.
            ip: Desde dónde, si vino por HTTP.
            action: ``search.deleted`` o ``search.restored``.
        """
        ...


@dataclass(frozen=True, slots=True)
class HistoryScope:
    """Qué búsquedas muestra el historial.

    Attributes:
        owner: Solo las de esta persona; ``None`` = las de todos (superusuario
            con «Ver de todos»).
        include_automatic: Sumar las corridas automáticas (del superusuario).
    """

    owner: str | None
    include_automatic: bool = False


class SearchReaderPort(Protocol):
    """Lecturas de búsquedas para la API. Una búsqueda eliminada no se lee."""

    async def search_detail(self, search_id: UUID) -> SearchDetail | None:
        """Una búsqueda.

        Args:
            search_id: Id.

        Returns:
            La búsqueda, o ``None`` si no existe.
        """
        ...

    async def history(
        self, scope: HistoryScope, after: TimeCursor | None, limit: int
    ) -> list[SearchDetail]:
        """Búsquedas del historial, de la más reciente a la más vieja.

        La seguridad por filas (ADR-0042) ya impide ver búsquedas ajenas a un
        usuario normal; ``scope`` decide qué muestra el historial dentro de
        lo que la persona puede ver.

        Args:
            scope: De quién.
            after: Cursor de la página anterior.
            limit: Cuántas como máximo.

        Returns:
            Las búsquedas de la página.
        """
        ...


@dataclass(frozen=True, slots=True)
class PreviousRun:
    """La corrida automática anterior a otra y las notas que ya trajo.

    Sirve para que el reporte separe lo nuevo de lo ya reportado: en la
    auditoría del 27/10/2026, el 88 al 94 % de las notas de cada corrida ya
    venía en la anterior, cuando cada una cubría hoy y ayer (ADR-0034). Con la
    ventana por horas (ADR-0031) sirve para los hechos que se siguen publicando.

    Attributes:
        search_id: La corrida anterior.
        scheduled_for: Su hora programada, si la tiene.
        article_ids: Todas las notas que encontró, relevantes o no.
    """

    search_id: UUID
    scheduled_for: datetime | None
    article_ids: frozenset[int]


class PreviousRunPort(Protocol):
    """Encuentra la corrida automática anterior a una búsqueda."""

    async def previous_automatic_run(self, search_id: UUID) -> PreviousRun | None:
        """La última corrida automática terminada del mismo tema, creada antes que esta.

        Args:
            search_id: La búsqueda de referencia.

        Returns:
            La corrida anterior, o ``None`` si no hay (o si se eliminó).
        """
        ...


class InRegion(StrEnum):
    """Filtro de las notas por región (las tres listas de la pantalla)."""

    INSIDE = "true"
    OUTSIDE = "false"
    UNLOCATED = "none"
    # Todas, también las de fuera (para revisar o auditar una búsqueda).
    ALL = "all"


@dataclass(frozen=True, slots=True)
class ArticleFilters:
    """Qué notas de una búsqueda se quieren.

    Attributes:
        relevant_only: Solo las relevantes para algún concepto (por defecto).
        in_region: Dentro, fuera o sin ubicación. ``None`` (por defecto) =
            dentro y sin ubicación: las de fuera de la región no cuentan en la
            lista, el globo, los conteos ni el reporte (Benji, 09/11/2026);
            se ven pidiendo ``OUTSIDE``.
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
class CategoryView:
    """La categoría de una nota, como se muestra (F12.4, ADR-0029).

    Attributes:
        category_id: Id en ``categories``.
        name: Nombre («Armas y explosivos»).
        color: Color, cuando se decida.
        symbol: Símbolo, cuando se decida.
    """

    category_id: int
    name: str
    color: str | None = None
    symbol: str | None = None


@dataclass(frozen=True, slots=True)
class CategoryCount:
    """Cuántas notas de una búsqueda hay en una categoría.

    Attributes:
        category: La categoría, o ``None`` para las notas todavía sin clasificar.
        count: Notas.
    """

    category: CategoryView | None
    count: int


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
        story_id: Historia a la que pertenece (id de su primera nota, ADR-0026),
            o ``None`` si está sola.
        category: El delito del que trata (ADR-0029), o ``None`` si falta
            clasificarla.
        category_raw: Etiqueta libre que propuso la IA.
        authority: Quién actúa en el hecho (ADR-0030), o ``None`` si falta
            clasificarla. Los juicios ya traen aplicada la regla de su concepto.
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
    story_id: int | None = None
    category: CategoryView | None = None
    category_raw: str | None = None
    authority: Authority | None = None


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

    async def category_counts(
        self, search_id: UUID, filters: ArticleFilters
    ) -> list[CategoryCount]:
        """Cuántas notas de la búsqueda hay en cada categoría (F12.4).

        Args:
            search_id: Búsqueda.
            filters: Los mismos filtros de la lista de notas.

        Returns:
            Una por categoría con notas (incluidas las sin clasificar).
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
