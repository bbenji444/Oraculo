"""Puertos para guardar una búsqueda y sus notas (especificación §6 y §9).

- ``SearchStorePort``: la fila de ``searches`` (con sus conceptos copiados),
  su avance, sus errores por nota y su cierre con bitácora.
- ``ArticleStorePort``: las notas deduplicadas (``articles``), su texto para
  procesar, lo que aportó la IA, sus ubicaciones y qué encontró cada
  búsqueda (``search_results``).

Las implementaciones están en
``app/adapters/persistence/search_repository.py``; las pruebas usan
versiones en memoria.

No hace: no decide nada (las reglas están en ``app.domain.search`` y en el
caso de uso ``RunSearch``).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.application.audit import Actor
from app.application.ports.llm import EnrichmentResult
from app.domain.dedupe import DedupedArticle
from app.domain.enrichment import LLMUsage
from app.domain.extraction import ProcessingText
from app.domain.geocoding import Mention, Resolution
from app.domain.search import SearchStatus, Stage


@dataclass(frozen=True, slots=True)
class SearchConcept:
    """Un concepto tal como estaba al momento de buscar (``search_concepts``).

    Cumple ``ConceptTerms``: ``build_queries`` lo acepta directo.

    Attributes:
        concept_id: Id del concepto.
        name: Nombre.
        description: Qué cubre (se lee del concepto vigente; sirve a la IA).
        keywords: Palabras clave copiadas.
        exclude_terms: Exclusiones copiadas.
    """

    concept_id: int
    name: str
    description: str
    keywords: tuple[str, ...]
    exclude_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NewSearch:
    """Lo necesario para crear una búsqueda en ``pending``.

    Attributes:
        user_id: Quién la pidió.
        region_id: Región buscada.
        date_from: Primer día (hora de la Ciudad de México).
        date_to: Último día.
        concepts: Conceptos copiados.
        queries_planned: Consultas planeadas.
        credits_estimated: Créditos estimados.
    """

    user_id: str
    region_id: int
    date_from: date
    date_to: date
    concepts: tuple[SearchConcept, ...]
    queries_planned: int
    credits_estimated: int


@dataclass(frozen=True, slots=True)
class StoredSearch:
    """Una búsqueda guardada, lista para correr.

    Attributes:
        search_id: Id.
        user_id: Quién la pidió.
        region_id: Región buscada.
        region_code: Clave de esa región (INEGI o ISO-A3).
        date_from: Primer día.
        date_to: Último día.
        status: Estado actual.
        concepts: Conceptos copiados al crearla.
    """

    search_id: UUID
    user_id: str
    region_id: int
    region_code: str
    date_from: date
    date_to: date
    status: SearchStatus
    concepts: tuple[SearchConcept, ...]


@dataclass(frozen=True, slots=True)
class ProcessingErrorRecord:
    """Un error de una nota o de la búsqueda (``processing_errors``).

    Attributes:
        search_id: Búsqueda.
        stage: Etapa en la que falló.
        error_type: Tipo de error (nombre de la excepción).
        message: Qué pasó, en español.
        article_id: Nota, si el error es de una nota.
        payload: Datos para depurar (nunca llaves ni el texto completo).
    """

    search_id: UUID
    stage: Stage
    error_type: str
    message: str
    article_id: int | None = None
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchClosing:
    """Cómo terminó una búsqueda, para cerrar su fila y la bitácora.

    Attributes:
        status: ``completed``, ``partial`` o ``failed``.
        progress: Avance final (conteos por etapa).
        credits_used: Créditos de SearchApi gastados.
        llm_usage: Tokens de la IA.
        llm_cost_usd: Costo estimado de la IA.
        results_count: Notas distintas encontradas.
        error_summary: Resumen de lo que falló, si algo falló.
        queries_executed: Consultas enviadas (texto y proveedor), para la
            bitácora (CLAUDE.md §8).
    """

    status: SearchStatus
    progress: Mapping[str, object]
    credits_used: int
    llm_usage: LLMUsage
    llm_cost_usd: float
    results_count: int
    error_summary: str | None
    queries_executed: tuple[Mapping[str, object], ...] = ()


class SearchStorePort(Protocol):
    """Fila de ``searches`` y lo que cuelga de ella."""

    async def create(self, search: NewSearch) -> UUID:
        """Crea la búsqueda en ``pending`` con sus conceptos copiados.

        Args:
            search: Datos de la búsqueda.

        Returns:
            Su id.
        """
        ...

    async def load(self, search_id: UUID) -> StoredSearch | None:
        """Lee una búsqueda.

        Args:
            search_id: Id.

        Returns:
            La búsqueda, o ``None`` si no existe.
        """
        ...

    async def start(self, search_id: UUID) -> None:
        """Pasa la búsqueda a ``running`` y anota la hora de inicio.

        Args:
            search_id: Id.
        """
        ...

    async def set_progress(self, search_id: UUID, progress: Mapping[str, object]) -> None:
        """Guarda el avance (etapa actual y conteos) para mostrarlo.

        Args:
            search_id: Id.
            progress: Avance serializable a JSON.
        """
        ...

    async def record_error(self, error: ProcessingErrorRecord) -> None:
        """Anota un error sin detener la búsqueda.

        Args:
            error: El error.
        """
        ...

    async def finish(self, search_id: UUID, closing: SearchClosing, actor: Actor) -> None:
        """Cierra la búsqueda y la anota en la bitácora, en una transacción.

        Args:
            search_id: Id.
            closing: Cómo terminó.
            actor: Quién la pidió.
        """
        ...


@dataclass(frozen=True, slots=True)
class StoredArticle:
    """Una nota ya guardada y lo que se sabe de ella.

    Attributes:
        article_id: Id en ``articles``.
        prompt_version: Versión de prompt con la que se enriqueció bien, o
            ``None`` si no se ha enriquecido.
        concept_ids: Conceptos que ya tienen juicio de relevancia.
        primary_code: Clave de su ubicación principal, si tiene.
    """

    article_id: int
    prompt_version: str | None = None
    concept_ids: frozenset[int] = frozenset()
    primary_code: str | None = None

    def reusable_for(self, prompt_version: str, concept_ids: frozenset[int]) -> bool:
        """Dice si su enriquecimiento sirve para esta búsqueda (caché de §10).

        Args:
            prompt_version: Versión vigente del prompt.
            concept_ids: Conceptos de la búsqueda.

        Returns:
            ``True`` si se enriqueció con la misma versión y ya juzgó todos
            esos conceptos.
        """
        return self.prompt_version == prompt_version and concept_ids <= self.concept_ids


@dataclass(frozen=True, slots=True)
class SearchResultRow:
    """Una nota que encontró una búsqueda, con un proveedor (``search_results``).

    Attributes:
        article_id: Nota.
        provider: Proveedor que la encontró.
        provider_rank: Posición en sus resultados.
        in_region: Si cae en la región buscada (``None``: sin ubicación).
    """

    article_id: int
    provider: str
    provider_rank: int
    in_region: bool | None


class ArticleStorePort(Protocol):
    """Notas, su texto, su enriquecimiento y sus ubicaciones."""

    async def upsert(self, articles: Sequence[DedupedArticle]) -> list[StoredArticle]:
        """Guarda las notas nuevas y devuelve todas con lo que ya se sabía de ellas.

        Args:
            articles: Notas sin duplicados.

        Returns:
            Una por nota, en el mismo orden.
        """
        ...

    async def save_text(self, article_id: int, text: ProcessingText) -> None:
        """Guarda el texto para procesar y cómo se obtuvo.

        Args:
            article_id: Nota.
            text: Texto y su estado (``ok`` o ``fallback``).
        """
        ...

    async def save_enrichment(
        self, article_id: int, result: EnrichmentResult, resolutions: Sequence[Resolution]
    ) -> None:
        """Guarda lo que aportó la IA y las ubicaciones resueltas, en una transacción.

        Args:
            article_id: Nota.
            result: Respuesta de la IA.
            resolutions: Menciones resueltas contra el catálogo (reemplazan
                a las anteriores).
        """
        ...

    async def mark_enrichment_failed(self, article_id: int) -> None:
        """Marca que la IA no pudo con la nota (se reintenta en otra búsqueda).

        Args:
            article_id: Nota.
        """
        ...

    async def link_results(self, search_id: UUID, rows: Sequence[SearchResultRow]) -> None:
        """Anota qué notas encontró la búsqueda.

        Args:
            search_id: Búsqueda.
            rows: Una por nota y proveedor.
        """
        ...


@dataclass(frozen=True, slots=True)
class ArticleMentions:
    """Las menciones de lugar guardadas de una nota de una búsqueda.

    Attributes:
        article_id: Nota.
        title: Título (para mostrar el antes y después).
        mentions: Menciones con las pistas que dio la IA (en notas anteriores
            a la migración 0014 solo traen texto, papel y, si era otro
            país, el país).
        primary_code: Clave de la ubicación principal actual, si tiene.
    """

    article_id: int
    title: str
    mentions: tuple[Mention, ...]
    primary_code: str | None


class RelocationStorePort(Protocol):
    """Lo necesario para volver a ubicar notas sin pagarle otra vez a la IA."""

    async def search_mentions(self, search_id: UUID) -> list[ArticleMentions]:
        """Notas de una búsqueda con sus menciones guardadas.

        Args:
            search_id: Búsqueda.

        Returns:
            Una por nota encontrada, enriquecida o no.
        """
        ...

    async def save_locations(self, article_id: int, resolutions: Sequence[Resolution]) -> None:
        """Reemplaza las ubicaciones de una nota.

        Args:
            article_id: Nota.
            resolutions: Menciones resueltas de nuevo.
        """
        ...

    async def set_in_region(self, search_id: UUID, article_id: int, in_region: bool | None) -> None:
        """Actualiza si la nota cae en la región buscada.

        Args:
            search_id: Búsqueda.
            article_id: Nota.
            in_region: Nuevo valor (``None``: sin ubicación).
        """
        ...

    async def merge_progress(self, search_id: UUID, values: Mapping[str, object]) -> None:
        """Actualiza solo algunos conteos del avance de la búsqueda.

        Args:
            search_id: Búsqueda.
            values: Conteos nuevos (los demás se conservan).
        """
        ...


@dataclass(frozen=True, slots=True)
class StoredText:
    """El texto guardado de una nota, para volver a pasarlo por la IA.

    Attributes:
        article_id: Nota.
        title: Título.
        text: Texto que se procesó (cuerpo o título + fragmento).
        published_at: Fecha de publicación, si se conoce.
    """

    article_id: int
    title: str
    text: str
    published_at: datetime | None


class ReprocessStorePort(RelocationStorePort, Protocol):
    """Lo necesario para volver a pasar por la IA las notas de una búsqueda."""

    async def search_texts(self, search_id: UUID) -> list[StoredText]:
        """Notas de una búsqueda que todavía tienen su texto guardado.

        Args:
            search_id: Búsqueda.

        Returns:
            Las que no han pasado la retención de ``article_texts``.
        """
        ...

    async def save_enrichment(
        self, article_id: int, result: EnrichmentResult, resolutions: Sequence[Resolution]
    ) -> None:
        """Ver ``ArticleStorePort.save_enrichment``."""
        ...

    async def add_llm_usage(
        self, search_id: UUID, usage: LLMUsage, cost_usd: float, actor: Actor
    ) -> None:
        """Suma lo gastado en reprocesar al total de la búsqueda y lo anota en la bitácora.

        Args:
            search_id: Búsqueda.
            usage: Tokens gastados.
            cost_usd: Costo estimado.
            actor: Quién lo pidió.
        """
        ...
