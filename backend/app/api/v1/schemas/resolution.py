"""Esquemas de la resolución de entidades de un caso (Fase 9.5, §9.8).

La sugerencia trae las dos entidades completas (con sus citas) para verlas
lado a lado, el motivo con su etiqueta en español y cuál se propone que
quede.

No hace: no valida reglas de negocio (eso es el dominio).
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.api.v1.schemas.entities import EntityOut
from app.application.use_cases.resolution import MergeProposal
from app.domain.entity_resolution import MERGE_REASON_LABEL, MergeReason


class MergeIn(BaseModel):
    """Cuerpo de «Son la misma»: cuál queda y cuál se une a ella."""

    case_id: UUID
    keep_id: int = Field(description="La que queda (la confirmada, si una lo está).")
    merge_id: int = Field(description="La que se une a ella.")


class DismissMergeIn(BaseModel):
    """Cuerpo de «No son la misma»."""

    case_id: UUID
    first_id: int
    second_id: int


class SplitIn(BaseModel):
    """Cuerpo de «Separar menciones»: cuáles pasan a una sugerencia nueva."""

    case_id: UUID
    mention_ids: list[int] = Field(min_length=1, description="Menciones propias de la entidad.")


class DismissOut(BaseModel):
    """Respuesta de «No son la misma»."""

    dismissed: bool = Field(description="False si ya estaba descartado.")


class MergeSuggestionOut(BaseModel):
    """Dos entidades del caso que podrían ser la misma."""

    first: EntityOut
    second: EntityOut
    reason: MergeReason
    reason_label: str
    reasons: list[MergeReason]
    keep_id: int

    @classmethod
    def from_proposal(cls, p: MergeProposal) -> "MergeSuggestionOut":
        """Convierte la sugerencia del caso de uso."""
        return cls(
            first=EntityOut.from_entity(p.first),
            second=EntityOut.from_entity(p.second),
            reason=p.reason,
            reason_label=MERGE_REASON_LABEL[p.reason],
            reasons=[r for r in MergeReason if r in p.reasons],
            keep_id=p.keep_id,
        )


class MergeSuggestionsOut(BaseModel):
    """Respuesta de ``GET /cases/{id}/merge-suggestions``."""

    items: list[MergeSuggestionOut]
