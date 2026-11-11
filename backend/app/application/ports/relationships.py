"""Puerto de los vínculos entre entidades de un caso (Fase 9.5, decisiones D6 a D8).

``RelationshipRepositoryPort`` lo implementa ``PostgresRelationshipRepository``
(``app/adapters/persistence/relationships_repository.py``); las pruebas usan
una versión en memoria.

Los vínculos por coocurrencia se calculan al leer y solo se guardan cuando
alguien los revisa: por eso un vínculo se identifica por su llave (las dos
entidades y el tipo) y no siempre por un id.

No hace: no decide permisos ni valida lo que escribe el analista (casos de
uso y dominio).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.audit import AuditEntry
from app.domain.investigation import (
    EntityType,
    LegalStatus,
    Origin,
    RelationshipType,
    ReviewStatus,
)
from app.domain.relationships import LinkStrength, link_reason, link_strength


@dataclass(frozen=True, slots=True)
class RelationshipEnd:
    """Una de las dos entidades del vínculo, con lo que se muestra de ella.

    Attributes:
        entity_id: Entidad (la raíz de su grupo de fusión).
        type: Tipo.
        label: Nombre.
        legal_status: Estatus legal (solo personas), siempre visible (ADR-0105).
    """

    entity_id: int
    type: EntityType
    label: str
    legal_status: LegalStatus | None


@dataclass(frozen=True, slots=True)
class SharedArticle:
    """Una nota del caso donde aparecen las dos entidades: la evidencia del vínculo.

    Attributes:
        article_id: Nota.
        title: Título.
        url: Liga a la nota original.
        published_at: Fecha de la nota.
        same_event: Si en esta nota las dos participan en el hecho (rol
            ``event`` en las dos) y no solo se nombran (F12, ADR-0107).
    """

    article_id: int
    title: str
    url: str
    published_at: datetime | None
    same_event: bool = False


@dataclass(frozen=True, slots=True)
class RelationshipKey:
    """Lo que identifica a un vínculo dentro de un caso.

    En los vínculos simétricos va primero el id menor (``ordered_pair``).

    Attributes:
        entity_a: Primera entidad.
        entity_b: Segunda entidad.
        type: Tipo de vínculo.
    """

    entity_a: int
    entity_b: int
    type: RelationshipType


@dataclass(frozen=True, slots=True)
class RelationshipView:
    """Un vínculo del caso como lo ve el analista.

    Attributes:
        relationship_id: Id si ya está guardado; ``None`` si es una
            sugerencia por coocurrencia que nadie ha revisado.
        entity_a: Primera entidad.
        entity_b: Segunda entidad.
        type: Tipo.
        custom_label: Etiqueta propia (solo ``custom``).
        origin: Coocurrencia, IA o humano (ADR-0105).
        confidence: De 0 a 1.
        review_status: Sugerido, confirmado o descartado (ADR-0104).
        reviewed_by: Quién lo revisó o lo creó.
        reviewed_at: Cuándo.
        notes: Nota del analista.
        shared_articles: Notas del caso donde aparecen las dos.
    """

    relationship_id: int | None
    entity_a: RelationshipEnd
    entity_b: RelationshipEnd
    type: RelationshipType
    custom_label: str | None
    origin: Origin
    confidence: float
    review_status: ReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    notes: str | None
    shared_articles: tuple[SharedArticle, ...]

    @property
    def key(self) -> RelationshipKey:
        """Las dos entidades y el tipo."""
        return RelationshipKey(self.entity_a.entity_id, self.entity_b.entity_id, self.type)

    @property
    def same_event_count(self) -> int:
        """En cuántas notas del caso las dos participan en el hecho."""
        return sum(1 for article in self.shared_articles if article.same_event)

    @property
    def strength(self) -> LinkStrength:
        """Qué tan útil es para investigar (``link_strength``, ADR-0107)."""
        return link_strength(self.origin, self.same_event_count)

    @property
    def reason(self) -> str:
        """Por qué se relacionan, en una frase (``link_reason``)."""
        return link_reason(self.origin, self.same_event_count, len(self.shared_articles))


@dataclass(frozen=True, slots=True)
class RelationshipWrite:
    """Lo que se guarda al revisar o crear un vínculo.

    Attributes:
        relationship_id: Id del vínculo guardado que se actualiza, o ``None``
            para guardar uno nuevo con ``key``.
        key: Entidades y tipo (para guardar uno nuevo).
        custom_label: Etiqueta propia (solo ``custom``).
        origin: Origen con el que se guarda uno nuevo.
        confidence: Confianza con la que se guarda uno nuevo.
        review_status: Confirmado o descartado.
        reviewer: Quién firma.
        notes: Nota nueva; ``None`` deja la que tenía.
    """

    relationship_id: int | None
    key: RelationshipKey
    custom_label: str | None
    origin: Origin
    confidence: float
    review_status: ReviewStatus
    reviewer: str
    notes: str | None


class RelationshipRepositoryPort(Protocol):
    """Vínculos de los casos: los derivados y los guardados."""

    async def list_case(self, case_id: UUID) -> list[RelationshipView]:
        """Todos los vínculos entre entidades confirmadas del caso (D6).

        Junta los calculados por coocurrencia (entidades confirmadas que
        comparten notas del caso) con los guardados; si un calculado ya se
        revisó, gana lo guardado. Cada entidad se muestra como la raíz de su
        grupo de fusión.

        Args:
            case_id: Caso.

        Returns:
            Los vínculos, sin orden particular.
        """
        ...

    async def save(self, case_id: UUID, write: RelationshipWrite, audit: AuditEntry) -> None:
        """Guarda una revisión o un vínculo nuevo, con firma y bitácora.

        Args:
            case_id: Caso (la bitácora se registra sobre él).
            write: Qué se guarda.
            audit: Registro de la bitácora.
        """
        ...

    async def save_many(
        self, case_id: UUID, items: Sequence[tuple[RelationshipWrite, AuditEntry]]
    ) -> None:
        """Guarda varias revisiones en una sola transacción (F12, ADR-0107).

        Cada una con su firma y su entrada de la bitácora; si una falla, no
        se guarda ninguna.

        Args:
            case_id: Caso (la bitácora se registra sobre él).
            items: Qué se guarda de cada vínculo y su registro de la bitácora.
        """
        ...


def find(views: Sequence[RelationshipView], key: RelationshipKey) -> RelationshipView | None:
    """El vínculo con esa llave, si existe.

    Args:
        views: Vínculos del caso.
        key: Entidades y tipo.

    Returns:
        El vínculo, o ``None``.
    """
    return next((view for view in views if view.key == key), None)
