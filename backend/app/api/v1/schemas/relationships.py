"""Esquemas de los vínculos entre entidades de un caso (Fase 9.5, D6 a D8).

La salida trae cada valor con su etiqueta en español ("aparecen juntas",
"aparecen en la misma nota") y el estatus legal de las personas siempre
visible (§9.10). Un vínculo sugerido por coocurrencia todavía no tiene id:
se revisa con sus dos entidades y su tipo.

No hace: no valida reglas de negocio (eso es el dominio).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.v1.schemas.entities import BulkActionIn
from app.application.ports.relationships import (
    RelationshipEnd,
    RelationshipView,
    SharedArticle,
)
from app.application.use_cases.relationships import CaseRelationships
from app.domain.investigation import (
    ENTITY_TYPE_LABEL,
    LEGAL_STATUS_LABEL,
    ORIGIN_LABEL,
    RELATIONSHIP_LABEL,
    REVIEW_STATUS_LABEL,
    SYMMETRIC_RELATIONSHIPS,
    LegalStatus,
    Origin,
    RelationshipType,
    ReviewStatus,
)
from app.domain.relationships import CUSTOM_LABEL_MAX_CHARS, RELATIONSHIP_NOTES_MAX_CHARS

# El dominio valida el largo ya sin espacios de más (manual_relationship); aquí
# solo se frena un cuerpo desmedido antes de llegar a él.
_RAW_SLACK = 2


class RelationshipIn(BaseModel):
    """Cuerpo de «Nuevo vínculo»."""

    case_id: UUID
    entity_a: int = Field(description="En los dirigidos, la que «es dueño de», «empleador»…")
    entity_b: int
    type: str = Field(description="appears_with, same_event, family, associate, employer, …")
    custom_label: str | None = Field(default=None, max_length=CUSTOM_LABEL_MAX_CHARS * _RAW_SLACK)
    notes: str | None = Field(default=None, max_length=RELATIONSHIP_NOTES_MAX_CHARS * _RAW_SLACK)


class RelationshipKeyIn(BaseModel):
    """La llave de un vínculo: sus dos entidades y su tipo, como los trae la lista."""

    entity_a: int
    entity_b: int
    type: RelationshipType


class RelationshipReviewIn(RelationshipKeyIn):
    """Cuerpo de confirmar o descartar: el caso y la llave del vínculo."""

    case_id: UUID


class RelationshipsReviewIn(BulkActionIn):
    """Cuerpo de ``POST /cases/{id}/relationships/review`` (F12, ADR-0107)."""

    items: list[RelationshipKeyIn]


class RelationshipEndOut(BaseModel):
    """Una de las dos entidades del vínculo."""

    id: int
    type: str
    type_label: str
    label: str
    legal_status: LegalStatus | None
    legal_status_label: str | None

    @classmethod
    def from_end(cls, e: RelationshipEnd) -> "RelationshipEndOut":
        """Convierte la punta del caso de uso."""
        return cls(
            id=e.entity_id,
            type=e.type.value,
            type_label=ENTITY_TYPE_LABEL[e.type],
            label=e.label,
            legal_status=e.legal_status,
            legal_status_label=LEGAL_STATUS_LABEL[e.legal_status] if e.legal_status else None,
        )


class SharedArticleOut(BaseModel):
    """Una nota del caso donde aparecen las dos entidades."""

    article_id: int
    title: str
    url: str
    published_at: datetime | None

    @classmethod
    def from_article(cls, a: SharedArticle) -> "SharedArticleOut":
        """Convierte la nota del caso de uso."""
        return cls(article_id=a.article_id, title=a.title, url=a.url, published_at=a.published_at)


class RelationshipOut(BaseModel):
    """Un vínculo del caso con su origen, su confianza y su evidencia."""

    id: int | None = Field(description="Nulo si es una sugerencia que nadie ha revisado.")
    entity_a: RelationshipEndOut
    entity_b: RelationshipEndOut
    type: RelationshipType
    type_label: str
    custom_label: str | None
    symmetric: bool = Field(description="Si A–B es lo mismo que B–A.")
    origin: Origin
    origin_label: str
    confidence: float
    review_status: ReviewStatus
    review_status_label: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    notes: str | None
    shared_articles: list[SharedArticleOut]

    @classmethod
    def from_view(cls, v: RelationshipView) -> "RelationshipOut":
        """Convierte el vínculo del caso de uso."""
        return cls(
            id=v.relationship_id,
            entity_a=RelationshipEndOut.from_end(v.entity_a),
            entity_b=RelationshipEndOut.from_end(v.entity_b),
            type=v.type,
            type_label=RELATIONSHIP_LABEL[v.type],
            custom_label=v.custom_label,
            symmetric=v.type in SYMMETRIC_RELATIONSHIPS,
            origin=v.origin,
            origin_label=ORIGIN_LABEL[v.origin],
            confidence=round(v.confidence, 2),
            review_status=v.review_status,
            review_status_label=REVIEW_STATUS_LABEL[v.review_status],
            reviewed_by=v.reviewed_by,
            reviewed_at=v.reviewed_at,
            notes=v.notes,
            shared_articles=[SharedArticleOut.from_article(a) for a in v.shared_articles],
        )


class CaseRelationshipsOut(BaseModel):
    """Respuesta de ``GET /cases/{id}/relationships``."""

    counts: dict[ReviewStatus, int]
    items: list[RelationshipOut]

    @classmethod
    def from_view(cls, view: CaseRelationships) -> "CaseRelationshipsOut":
        """Convierte la vista del caso de uso."""
        return cls(counts=view.counts, items=[RelationshipOut.from_view(v) for v in view.items])
