"""Puertos de las entidades de un caso: guardarlas, leerlas y encolar su extracción (Fase 9.4).

``EntityRepositoryPort`` lo implementa ``PostgresEntityRepository``
(``app/adapters/persistence/entities_repository.py``); ``EntityQueuePort``, la
cola de Celery. Las pruebas usan versiones en memoria.

No hace: no decide permisos ni revisa lo que propone la IA (eso son los casos
de uso y el dominio).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.audit import AuditEntry
from app.domain.enrichment import LLMUsage
from app.domain.entity_extraction import (
    CaseArticleEntitiesStatus,
    MentionHint,
    ReviewedProposals,
    TextSource,
    suggested_legal_status,
)
from app.domain.geocoding import MentionRole
from app.domain.investigation import EntityType, LegalStatus, ReviewStatus


@dataclass(frozen=True, slots=True)
class ArticleSource:
    """Una nota del caso con lo que hace falta para que la IA la lea.

    Attributes:
        article_id: Nota.
        status: En qué va su análisis en este caso.
        title: Título.
        snippet: Fragmento del proveedor.
        stored_body: Texto guardado (``article_texts``), si no se ha borrado.
        full_text: Si ese texto es el cuerpo extraído y no título + fragmento.
        published_at: Fecha de publicación, si se conoce.
    """

    article_id: int
    status: CaseArticleEntitiesStatus
    title: str
    snippet: str | None
    stored_body: str | None
    full_text: bool
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class StoredExtraction:
    """Lo que la IA respondió de una nota, ya revisado contra el texto.

    Attributes:
        article_id: Nota.
        prompt_version: Versión del prompt (``entities_v1``).
        model: Modelo que la leyó.
        source: Qué texto leyó.
        reviewed: Propuestas aceptadas y descartadas.
        usage: Tokens de esta llamada.
        cost_usd: Costo de esta llamada.
    """

    article_id: int
    prompt_version: str
    model: str
    source: TextSource
    reviewed: ReviewedProposals
    usage: LLMUsage
    cost_usd: float


@dataclass(frozen=True, slots=True)
class FailedExtraction:
    """Una lectura que no dio una respuesta válida (se cobra igual).

    Attributes:
        article_id: Nota.
        prompt_version: Versión del prompt.
        model: Modelo.
        source: Qué texto se le dio.
        usage: Tokens gastados en los intentos.
        cost_usd: Costo de los intentos.
        error: Qué falló, en español.
    """

    article_id: int
    prompt_version: str
    model: str
    source: TextSource
    usage: LLMUsage
    cost_usd: float
    error: str


@dataclass(frozen=True, slots=True)
class Materialized:
    """Cómo quedaron en el caso las propuestas de una nota.

    Attributes:
        created: Sugerencias nuevas.
        attached: Menciones que se sumaron a una sugerencia del caso con el
            mismo nombre y tipo (decisión D6).
        skipped: Menciones que ya estaban (la nota se había quitado y vuelto
            a agregar).
    """

    created: int
    attached: int
    skipped: int


@dataclass(frozen=True, slots=True)
class CaseAnalysis:
    """En qué va el análisis de las notas de un caso y cuánto lleva gastado.

    Attributes:
        articles: Notas del caso.
        pending: Sin pedir (las que ya estaban antes de la 9.4, o si la cola falló).
        queued: En la cola del worker.
        done: Ya leídas.
        failed: La IA no respondió bien; se pueden volver a pedir.
        skipped: Fuera del tope del caso.
        title_snippet: Leídas solo con título y fragmento (texto ya borrado).
        cost_usd: Lo que este caso pagó a la IA.
    """

    articles: int
    pending: int
    queued: int
    done: int
    failed: int
    skipped: int
    title_snippet: int
    cost_usd: float


@dataclass(frozen=True, slots=True)
class MentionView:
    """Una mención de la entidad: la evidencia que ve el analista.

    Attributes:
        mention_id: Id de la mención.
        article_id: Nota de donde salió.
        article_title: Título de la nota.
        article_url: Liga a la nota original.
        source_name: Medio.
        published_at: Fecha de la nota.
        mention_text: Nombre con que aparece.
        role: Si participa en el hecho o solo se nombra.
        legal_status_hint: Lo que dice esa nota de la persona.
        confidence: Confianza de la IA.
        evidence_span: La cita de la nota.
    """

    mention_id: int
    article_id: int
    article_title: str
    article_url: str
    source_name: str | None
    published_at: datetime | None
    mention_text: str
    role: MentionRole
    legal_status_hint: LegalStatus | None
    confidence: float
    evidence_span: str


@dataclass(frozen=True, slots=True)
class CaseEntity:
    """Una entidad de un caso con sus menciones en las notas del caso.

    Attributes:
        entity_id: Id.
        type: Tipo.
        label: Nombre.
        aliases: Otros nombres.
        review_status: Sugerida, confirmada o descartada (ADR-0104).
        legal_status: El que eligió quien la confirmó (solo personas).
        reviewed_by: Quién la revisó.
        reviewed_at: Cuándo.
        region_id: Región del catálogo, si es un lugar ya ubicado (D8).
        region_name: Nombre de esa región para mostrar.
        mentions: Menciones en notas que siguen en el caso, de la más
            reciente a la más vieja.
    """

    entity_id: int
    type: EntityType
    label: str
    aliases: tuple[str, ...]
    review_status: ReviewStatus
    legal_status: LegalStatus | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    region_id: int | None
    region_name: str | None
    mentions: tuple[MentionView, ...]

    @property
    def suggested_legal_status(self) -> LegalStatus | None:
        """Estatus que se propone al confirmar: el de la nota más reciente que lo dice (D7)."""
        if self.type is not EntityType.PERSON:
            return None
        return suggested_legal_status(
            MentionHint(m.published_at, m.mention_id, m.legal_status_hint) for m in self.mentions
        )

    @property
    def article_count(self) -> int:
        """En cuántas notas distintas del caso aparece."""
        return len({m.article_id for m in self.mentions})


class EntityRepositoryPort(Protocol):
    """Entidades de los casos y lo que la IA leyó de cada nota."""

    async def article_source(self, case_id: UUID, article_id: int) -> ArticleSource | None:
        """Una nota del caso con su texto, para dárselo a la IA.

        Args:
            case_id: Caso.
            article_id: Nota.

        Returns:
            La nota, o ``None`` si ya no está en el caso.
        """
        ...

    async def done_count(self, case_id: UUID) -> int:
        """Cuántas notas del caso ya se leyeron (para el tope del caso).

        Args:
            case_id: Caso.

        Returns:
            Notas en ``done``.
        """
        ...

    async def get_extraction(self, article_id: int, prompt_version: str) -> StoredExtraction | None:
        """La lectura correcta de una nota con esa versión de prompt, si existe.

        Args:
            article_id: Nota.
            prompt_version: Versión del prompt.

        Returns:
            La lectura guardada (para reutilizarla sin pagar), o ``None``.
        """
        ...

    async def save_extraction(self, extraction: StoredExtraction) -> None:
        """Guarda una lectura correcta (suma los tokens de intentos fallidos anteriores).

        Args:
            extraction: La lectura revisada.
        """
        ...

    async def save_failure(
        self, case_id: UUID, failure: FailedExtraction, audit: AuditEntry
    ) -> None:
        """Registra una lectura fallida, marca la nota ``failed`` y escribe la bitácora.

        Args:
            case_id: Caso que la pidió (paga lo gastado).
            failure: Lo que falló y lo gastado.
            audit: Registro de la bitácora.
        """
        ...

    async def materialize(
        self, case_id: UUID, extraction: StoredExtraction, cost_usd: float, audit: AuditEntry
    ) -> Materialized | None:
        """Convierte las propuestas de una nota en sugerencias del caso (decisión D6).

        En una sola transacción, y de a una nota por caso a la vez para que dos
        notas con la misma persona no creen dos sugerencias: agrupa por nombre
        normalizado y tipo dentro del caso, liga los lugares a la región ya
        ubicada de la misma nota (D8), marca la nota ``done``, suma su costo y
        escribe la bitácora.

        Args:
            case_id: Caso.
            extraction: Lectura revisada de la nota.
            cost_usd: Lo que paga este caso (0 si se reutilizó).
            audit: Registro de la bitácora.

        Returns:
            Cuántas sugerencias se crearon o crecieron, o ``None`` si la nota
            ya no está en el caso.
        """
        ...

    async def set_status(
        self, case_id: UUID, article_ids: Sequence[int], status: CaseArticleEntitiesStatus
    ) -> None:
        """Cambia el estado de análisis de notas del caso.

        Args:
            case_id: Caso.
            article_ids: Notas.
            status: Estado nuevo.
        """
        ...

    async def to_analyze(self, case_id: UUID, limit: int) -> list[int]:
        """Notas del caso que faltan por leer (``pending`` o ``failed``), las más viejas primero.

        Args:
            case_id: Caso.
            limit: Cuántas como máximo.

        Returns:
            Ids de las notas.
        """
        ...

    async def analysis(self, case_id: UUID) -> CaseAnalysis:
        """En qué va el análisis del caso y cuánto lleva gastado.

        Args:
            case_id: Caso.

        Returns:
            Conteos por estado y costo.
        """
        ...

    async def list_entities(self, case_id: UUID, status: ReviewStatus) -> list[CaseEntity]:
        """Entidades del caso en un estado de revisión, con sus menciones.

        Una sugerencia cuyas menciones son todas de notas que se quitaron del
        caso no aparece (vuelve si la nota regresa).

        Args:
            case_id: Caso.
            status: Sugeridas, confirmadas o descartadas.

        Returns:
            Las entidades, sin orden particular.
        """
        ...

    async def review_counts(self, case_id: UUID) -> dict[ReviewStatus, int]:
        """Cuántas entidades del caso hay en cada estado (con la misma regla que la lista).

        Args:
            case_id: Caso.

        Returns:
            Un conteo por estado (0 si no hay).
        """
        ...

    async def get_entity(self, case_id: UUID, entity_id: int) -> CaseEntity | None:
        """Una entidad del caso.

        Args:
            case_id: Caso.
            entity_id: Entidad.

        Returns:
            La entidad, o ``None`` si no es de ese caso.
        """
        ...

    async def review(  # noqa: PLR0913 — cada dato de la revisión firmada, por nombre (*)
        self,
        case_id: UUID,
        entity_id: int,
        *,
        status: ReviewStatus,
        legal_status: LegalStatus | None,
        reviewer: str,
        audit: AuditEntry,
    ) -> CaseEntity:
        """Confirma o descarta una entidad con firma y bitácora, en una transacción.

        Args:
            case_id: Caso.
            entity_id: Entidad.
            status: Confirmada o descartada.
            legal_status: Estatus legal que queda (solo personas).
            reviewer: Quién revisa (``reviewed_by``).
            audit: Registro de la bitácora.

        Returns:
            La entidad como quedó.
        """
        ...


class EntityQueuePort(Protocol):
    """Manda una nota del caso al worker para que la IA la lea."""

    def enqueue(self, case_id: UUID, article_id: int, requested_by: str) -> None:
        """Encola la lectura.

        Args:
            case_id: Caso.
            article_id: Nota.
            requested_by: Quién la pidió (queda en la bitácora).
        """
        ...
