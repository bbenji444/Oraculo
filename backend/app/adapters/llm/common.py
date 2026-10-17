"""Lo que comparten los adaptadores de IA: prompt, esquema y validación (§10; ADR-0016).

Gemini y OpenAI reciben el mismo prompt versionado (``enrich_v1.md``) y su
respuesta se valida con el mismo modelo de Pydantic (``EnrichmentOut``).
Así, cambiar de proveedor no cambia lo que se pide ni lo que se acepta.

No hace: no llama a ninguna IA.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.application.ports.llm import EnrichmentRequest
from app.domain.enrichment import ConceptBrief, ConceptJudgement, Enrichment
from app.domain.geocoding import Mention, MentionRole
from app.domain.region import RegionLevel

PROMPT_VERSION = "enrich_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"
# Respuestas consistentes: se extraen datos, no se escribe creativo.
TEMPERATURE = 0.2
# Tope de la respuesta: un JSON con resumen, conceptos y lugares cabe de
# sobra; evita respuestas desbocadas que cuestan.
MAX_OUTPUT_TOKENS = 2048
# Se agrega al prompt en el reintento (§10: "se reintenta una vez con el error").
RETRY_NOTE = (
    "\n\nTu respuesta anterior no cumplió el esquema. Error: {error}\n"
    "Responde de nuevo SOLO con el JSON válido."
)
# Cuánto del error de validación se le devuelve a la IA.
RETRY_ERROR_CHARS = 500

LocationKind = Literal["country", "state", "municipality", "locality"]


class LocationOut(BaseModel):
    """Una mención de lugar en la respuesta."""

    mention: str = Field(min_length=1)
    kind_hint: LocationKind | None = None
    state_hint: str | None = None
    country: str | None = None
    role: Literal["event", "mentioned"]


class ConceptOut(BaseModel):
    """Relevancia para un concepto en la respuesta."""

    concept_id: int
    is_relevant: bool
    relevance_score: float = Field(ge=0, le=1)
    relevance_reason: str | None = None


class EnrichmentOut(BaseModel):
    """Esquema de la respuesta de la IA (salida esperada de §10)."""

    concepts: list[ConceptOut]
    summary: str | None = None
    event_type: str | None = None
    event_date: date | None = None
    locations: list[LocationOut] = Field(default_factory=list)


def _concepts_text(concepts: Sequence[ConceptBrief]) -> str:
    return "\n".join(
        f"- concept_id {c.concept_id}: {c.name}. {c.description} "
        f"(palabras clave: {', '.join(c.keywords)})"
        for c in concepts
    )


def build_prompt(request: EnrichmentRequest) -> str:
    """Llena la plantilla ``enrich_v1.md`` con la nota.

    Args:
        request: Nota y conceptos.

    Returns:
        El texto que se manda a la IA.
    """
    template = PROMPT_PATH.read_text(encoding="utf-8")
    published = request.published_at.date().isoformat() if request.published_at else "desconocida"
    return template.format(
        concepts=_concepts_text(request.concepts),
        published_at=published,
        title=request.title,
        text=request.text,
    )


def to_enrichment(out: EnrichmentOut, concept_ids: set[int]) -> Enrichment:
    """Convierte la respuesta validada al dominio.

    Args:
        out: Respuesta validada.
        concept_ids: Conceptos que se preguntaron (los demás se ignoran).

    Returns:
        El enriquecimiento.
    """
    return Enrichment(
        concepts=tuple(
            ConceptJudgement(c.concept_id, c.is_relevant, c.relevance_score, c.relevance_reason)
            for c in out.concepts
            if c.concept_id in concept_ids
        ),
        summary=out.summary,
        event_type=out.event_type,
        event_date=out.event_date,
        locations=tuple(
            Mention(
                text=loc.mention,
                role=MentionRole(loc.role),
                kind_hint=RegionLevel(loc.kind_hint) if loc.kind_hint else None,
                state_hint=loc.state_hint,
                country=loc.country,
            )
            for loc in out.locations
        ),
    )
