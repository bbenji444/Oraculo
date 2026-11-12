"""Esquemas de las entidades de un caso (Fases 9.4 y 9.5, historias H9.2 y §9.8; F12).

Desde F12 (ADR-0107) también el cuerpo y la respuesta de revisar en bloque.

La salida trae cada valor con su etiqueta en español ("persona", "señalado")
para que la interfaz no traduzca, y el estatus legal siempre visible (§9.10).

No hace: no valida reglas de negocio (eso es el dominio).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.application.ports.entities import CaseAnalysis, CaseEntity, MentionView
from app.application.use_cases.entities import CaseEntities, PendingRequest
from app.domain.bulk_review import BulkReviewResult
from app.domain.investigation import (
    ENTITY_TYPE_LABEL,
    LEGAL_STATUS_LABEL,
    REVIEW_STATUS_LABEL,
    LegalStatus,
    ReviewStatus,
)


def _legal_label(status: LegalStatus | None) -> str | None:
    return LEGAL_STATUS_LABEL[status] if status else None


class ReviewIn(BaseModel):
    """Cuerpo de confirmar o descartar: en qué caso se revisa."""

    case_id: UUID


class ConfirmIn(ReviewIn):
    """Cuerpo de confirmar: el estatus legal según la nota (obligatorio en personas)."""

    legal_status: LegalStatus | None = Field(
        default=None, description="Solo personas: mentioned, alleged, detained, charged, …"
    )


class MentionOut(BaseModel):
    """Una mención: la cita y la nota de donde salió."""

    id: int
    # Entidad dueña: la misma, o una que se le unió (9.5). Solo las propias se separan.
    entity_id: int
    article_id: int
    article_title: str
    article_url: str
    source_name: str | None
    published_at: datetime | None
    mention_text: str
    role: str
    legal_status_hint: LegalStatus | None
    legal_status_hint_label: str | None
    confidence: float
    evidence_span: str

    @classmethod
    def from_view(cls, m: MentionView) -> "MentionOut":
        """Convierte la mención del caso de uso."""
        return cls(
            id=m.mention_id,
            entity_id=m.entity_id,
            article_id=m.article_id,
            article_title=m.article_title,
            article_url=m.article_url,
            source_name=m.source_name,
            published_at=m.published_at,
            mention_text=m.mention_text,
            role=m.role.value,
            legal_status_hint=m.legal_status_hint,
            legal_status_hint_label=_legal_label(m.legal_status_hint),
            confidence=m.confidence,
            evidence_span=m.evidence_span,
        )


class MergedOut(BaseModel):
    """Una entidad que se unió a esta (9.5): se puede separar."""

    id: int
    label: str
    merged_into: int


class EntityOut(BaseModel):
    """Una entidad del caso con su evidencia."""

    id: int
    type: str
    type_label: str
    label: str
    aliases: list[str]
    review_status: ReviewStatus
    review_status_label: str
    legal_status: LegalStatus | None
    legal_status_label: str | None
    suggested_legal_status: LegalStatus | None
    suggested_legal_status_label: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    region_id: int | None
    region_name: str | None
    mention_count: int
    article_count: int
    mentions: list[MentionOut]
    merged: list[MergedOut]

    @classmethod
    def from_entity(cls, e: CaseEntity) -> "EntityOut":
        """Convierte la entidad del caso de uso."""
        suggested = e.suggested_legal_status
        return cls(
            id=e.entity_id,
            type=e.type.value,
            type_label=ENTITY_TYPE_LABEL[e.type],
            label=e.label,
            aliases=list(e.aliases),
            review_status=e.review_status,
            review_status_label=REVIEW_STATUS_LABEL[e.review_status],
            legal_status=e.legal_status,
            legal_status_label=_legal_label(e.legal_status),
            suggested_legal_status=suggested,
            suggested_legal_status_label=_legal_label(suggested),
            reviewed_by=e.reviewed_by,
            reviewed_at=e.reviewed_at,
            region_id=e.region_id,
            region_name=e.region_name,
            mention_count=len(e.mentions),
            article_count=e.article_count,
            mentions=[MentionOut.from_view(m) for m in e.mentions],
            merged=[
                MergedOut(id=m.entity_id, label=m.label, merged_into=m.merged_into)
                for m in e.merged
            ],
        )


class AnalysisOut(BaseModel):
    """En qué va la lectura de las notas del caso por la IA y cuánto costó."""

    articles: int
    pending: int
    queued: int
    done: int
    failed: int
    skipped: int
    title_snippet: int
    cost_usd: float
    estimated_pending_cost_usd: float

    @classmethod
    def from_analysis(cls, a: CaseAnalysis, estimated: float) -> "AnalysisOut":
        """Convierte el avance del caso de uso."""
        return cls(
            articles=a.articles,
            pending=a.pending,
            queued=a.queued,
            done=a.done,
            failed=a.failed,
            skipped=a.skipped,
            title_snippet=a.title_snippet,
            cost_usd=round(a.cost_usd, 6),
            estimated_pending_cost_usd=round(estimated, 6),
        )


class CaseEntitiesOut(BaseModel):
    """Respuesta de ``GET /cases/{id}/entities``."""

    analysis: AnalysisOut
    counts: dict[ReviewStatus, int]
    items: list[EntityOut]

    @classmethod
    def from_view(cls, view: CaseEntities) -> "CaseEntitiesOut":
        """Convierte la vista del caso de uso."""
        return cls(
            analysis=AnalysisOut.from_analysis(view.analysis, view.estimated_pending_cost_usd),
            counts=view.counts,
            items=[EntityOut.from_entity(e) for e in view.items],
        )


class ExtractOut(BaseModel):
    """Respuesta de "Analizar pendientes"."""

    queued: int
    estimated_cost_usd: float

    @classmethod
    def from_request(cls, r: PendingRequest) -> "ExtractOut":
        """Convierte el resultado del caso de uso."""
        return cls(queued=r.queued, estimated_cost_usd=round(r.estimated_cost_usd, 6))


class BulkActionIn(BaseModel):
    """Lo común de revisar en bloque entidades o vínculos (F12, ADR-0107)."""

    action: Literal["confirm", "discard"] = Field(description="confirm o discard.")

    @property
    def status(self) -> ReviewStatus:
        """La revisión que queda: confirmada o descartada."""
        return ReviewStatus.CONFIRMED if self.action == "confirm" else ReviewStatus.DISCARDED


class EntityDecisionIn(BaseModel):
    """Una entidad elegida para revisar en bloque."""

    entity_id: int
    legal_status: LegalStatus | None = Field(
        default=None, description="Solo al confirmar personas: el estatus que dice la nota."
    )


class EntitiesReviewIn(BulkActionIn):
    """Cuerpo de ``POST /cases/{id}/entities/review``."""

    items: list[EntityDecisionIn]


class BulkReviewOut(BaseModel):
    """Cómo quedó una revisión en bloque."""

    changed: int
    unchanged: int

    @classmethod
    def from_result(cls, result: BulkReviewResult) -> "BulkReviewOut":
        """Convierte el resultado del caso de uso."""
        return cls(changed=result.changed, unchanged=result.unchanged)
