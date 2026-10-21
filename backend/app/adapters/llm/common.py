"""Lo que comparten los adaptadores de IA: prompt, esquema y validación (§10; ADR-0016).

Gemini y OpenAI reciben el mismo prompt versionado (``enrich_v2.md`` para
enriquecer una nota, ``summary_v1.md`` para el resumen ejecutivo de un
reporte, ``entities_v1.md`` para proponer las entidades de una nota de un
caso) y su respuesta se valida con el mismo modelo de Pydantic
(``EnrichmentOut``, ``SummaryOut``, ``EntitiesOut``). Así, cambiar de
proveedor no cambia lo que se pide ni lo que se acepta.

No hace: no llama a ninguna IA.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.application.clock import MEXICO_CITY
from app.application.ports.llm import (
    EnrichmentRequest,
    EntityExtractionRequest,
    SummaryNote,
    SummaryRequest,
)
from app.domain.enrichment import ConceptBrief, ConceptJudgement, Enrichment
from app.domain.entity_extraction import RawProposal
from app.domain.geocoding import Mention, MentionRole
from app.domain.region import RegionLevel

# v2 (21/10/2026): pide el municipio de cada colonia o calle, marca al menos
# un lugar del hecho y fecha el hecho original en avances de casos (ADR-0020).
PROMPT_VERSION = "enrich_v2"
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

# Resumen ejecutivo de los reportes (§15, ADR-0018).
SUMMARY_PROMPT_VERSION = "summary_v1"
SUMMARY_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{SUMMARY_PROMPT_VERSION}.md"
# Unos 180 palabras de respuesta caben de sobra; el tope evita respuestas
# desbocadas que cuestan.
SUMMARY_MAX_OUTPUT_TOKENS = 1024
# Igual que el tope de notas que se enriquecen por búsqueda
# (LLM_MAX_ARTICLES_PER_SEARCH): a ~60 tokens por nota, el prompt queda
# en ~10 000 tokens (~0.001 USD con gpt-6-luna).
MAX_SUMMARY_NOTES = 150
_DAY = "%d/%m/%Y"

# Entidades de las notas de un caso (Fase 9.4, ADR-0103).
ENTITIES_PROMPT_VERSION = "entities_v1"
ENTITIES_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{ENTITIES_PROMPT_VERSION}.md"
# Cada entidad lleva su cita de hasta 300 caracteres (~100 tokens): 4,096
# alcanzan para ~30 entidades, más de las que trae una nota; el tope evita
# respuestas desbocadas que cuestan.
ENTITIES_MAX_OUTPUT_TOKENS = 4096


class LocationOut(BaseModel):
    """Una mención de lugar en la respuesta."""

    mention: str = Field(min_length=1)
    kind_hint: LocationKind | None = None
    state_hint: str | None = None
    municipality_hint: str | None = None
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
    """Llena la plantilla del prompt vigente (``PROMPT_VERSION``) con la nota.

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
                municipality_hint=loc.municipality_hint,
            )
            for loc in out.locations
        ),
    )


class SummaryOut(BaseModel):
    """Esquema de la respuesta del resumen ejecutivo."""

    # Sin espacios sobrantes; un texto vacío o solo de espacios no valida y se
    # reintenta (§10).
    executive_summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _summary_line(note: SummaryNote) -> str:
    # La fecha se muestra en hora de la Ciudad de México (CLAUDE.md §6.3).
    day = note.published_at.astimezone(MEXICO_CITY).strftime(_DAY) if note.published_at else None
    return (
        f"- [{day or 'sin fecha'}] {note.title} — {note.place or 'sin ubicación'}: {note.summary}"
    )


def build_summary_prompt(request: SummaryRequest) -> str:
    """Llena la plantilla ``summary_v1.md`` con las notas relevantes.

    Solo lleva título, fecha, lugar y el resumen ya generado de cada nota,
    nunca su texto (§8). Si hay más de ``MAX_SUMMARY_NOTES``, se mandan las
    primeras (las más recientes), pero el conteo dice cuántas son en total.

    Args:
        request: Búsqueda y notas relevantes.

    Returns:
        El texto que se manda a la IA.
    """
    template = SUMMARY_PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        concepts=", ".join(request.concepts),
        region=request.region,
        date_from=request.date_from.strftime(_DAY),
        date_to=request.date_to.strftime(_DAY),
        count=len(request.notes),
        notes="\n".join(_summary_line(n) for n in request.notes[:MAX_SUMMARY_NOTES]),
    )


class EntityOut(BaseModel):
    """Una entidad en la respuesta (salida esperada del plan §9.7).

    Tipo, papel y estatus legal se aceptan como texto: lo que no sea un valor
    conocido lo descarta o lo deja vacío la revisión del dominio
    (``review_proposals``), sin gastar un reintento.
    """

    type: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    role: str
    legal_status_hint: str | None = None
    confidence: float
    evidence_span: str


class EntitiesOut(BaseModel):
    """Esquema de la respuesta de ``entities_v1``."""

    entities: list[EntityOut]


def build_entities_prompt(request: EntityExtractionRequest) -> str:
    """Llena la plantilla ``entities_v1.md`` con la nota.

    Args:
        request: Título y texto de la nota.

    Returns:
        El texto que se manda a la IA.
    """
    template = ENTITIES_PROMPT_PATH.read_text(encoding="utf-8")
    published = request.published_at.date().isoformat() if request.published_at else "desconocida"
    return template.format(published_at=published, title=request.title, text=request.text)


def to_raw_proposals(out: EntitiesOut) -> tuple[RawProposal, ...]:
    """Convierte la respuesta validada a propuestas sin revisar.

    Args:
        out: Respuesta validada.

    Returns:
        Una propuesta por entidad, en el orden de la respuesta.
    """
    return tuple(
        RawProposal(
            type=e.type,
            label=e.label,
            aliases=tuple(e.aliases),
            role=e.role,
            legal_status_hint=e.legal_status_hint,
            confidence=e.confidence,
            evidence_span=e.evidence_span,
        )
        for e in out.entities
    )
