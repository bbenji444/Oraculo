"""Lo que comparten los adaptadores de IA: prompt, esquema y validación (§10; ADR-0016).

Gemini y OpenAI reciben el mismo prompt versionado (``enrich_v4.md`` para
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
    ClassificationLabel,
    ClassificationNote,
    ClassificationRequest,
    EnrichmentRequest,
    EntityExtractionRequest,
    SummaryNote,
    SummaryRequest,
)
from app.domain.authority import parse_authority
from app.domain.enrichment import ConceptBrief, ConceptJudgement, Enrichment
from app.domain.entity_extraction import RawProposal
from app.domain.geocoding import Mention, MentionRole
from app.domain.region import RegionLevel

# v2 (21/10/2026): pide el municipio de cada colonia o calle, marca al menos
# un lugar del hecho y fecha el hecho original en avances de casos (ADR-0020).
# v3 (28/10/2026): la fecha y el tipo son los de lo que la nota informa (la
# sentencia de hoy, no el delito de 2019), para que las corridas dejen fuera
# solo los hechos de otros días (ADR-0031).
PROMPT_VERSION = "enrich_v4"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"
# Respuestas consistentes: se extraen datos, no se escribe creativo.
TEMPERATURE = 0.2
# Tope de la respuesta: evita respuestas desbocadas que cuestan. Con 2048,
# las agendas de marchas (decenas de lugares) llegaban cortadas y la nota se
# quedaba sin resumen (prueba del 11/11/2026: 2 de 25). enrich_v4 además pide
# máximo 12 lugares; solo se cobra lo que de verdad se escribe.
MAX_OUTPUT_TOKENS = 3072
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


# Clasificación por categoría (F12.4, ADR-0029) y quién actúa (F12.5,
# ADR-0030): una llamada por lote. v2 agrega ``authority``; v3 cuenta como FGR
# sus nombramientos, a su titular y los juicios donde es parte; v4 (26/10/2026)
# pone lo que rodea a un caso penal (protestas, cartas, audiencias) en la
# categoría del delito, con la nueva «Seguridad nacional (traición a la
# patria)». Cambiar la versión hace que las notas se vuelvan a clasificar.
CLASSIFY_PROMPT_VERSION = "classify_v4"
CLASSIFY_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{CLASSIFY_PROMPT_VERSION}.md"
# Notas por llamada: con título y resumen (~80 tokens cada una) el prompt
# queda en ~2,600 tokens; más notas alargan la respuesta sin ahorrar mucho.
CLASSIFY_BATCH_SIZE = 25
# ~30 tokens por nota (id, categoría y etiqueta) × 25 caben de sobra.
CLASSIFY_MAX_OUTPUT_TOKENS = 2048
# Un resumen largo no ayuda a clasificar y encarece el lote.
CLASSIFY_SUMMARY_CHARS = 400
# Razones de la IA al leer la nota completa (una oración por concepto): con
# 300 caracteres caben dos o tres, que es lo que suele haber.
CLASSIFY_READING_NOTES_CHARS = 300


class ClassifiedItemOut(BaseModel):
    """Una nota clasificada en la respuesta de la IA."""

    id: int
    category: str
    label: str | None = None
    # Texto libre aquí; ``parse_authority`` toma lo que no reconoce como
    # ``sin_dato`` (Gemini no garantiza la lista cerrada como OpenAI).
    authority: str | None = None


class ClassificationOut(BaseModel):
    """Esquema de la respuesta de la clasificación."""

    items: list[ClassifiedItemOut]


def build_classify_prompt(request: ClassificationRequest) -> str:
    """Llena la plantilla ``classify_v4.md`` con el catálogo y el lote.

    Args:
        request: Notas (título y resumen, nunca el texto, §8) y catálogo.

    Returns:
        El texto que se manda a la IA.
    """
    template = CLASSIFY_PROMPT_PATH.read_text(encoding="utf-8")
    categories = "\n".join(f"- {c.name}: {c.description}" for c in request.categories)
    notes = "\n".join(_classify_line(n) for n in request.notes)
    return template.format(other=request.other, categories=categories, notes=notes)


def _classify_line(note: ClassificationNote) -> str:
    summary = (note.summary or "sin resumen")[:CLASSIFY_SUMMARY_CHARS]
    line = f"[{note.article_id}] {note.title} — {summary}"
    if note.reading_notes:
        # Lo que anotó la IA al leerla completa: dice quién actuó aunque el
        # resumen no lo diga (F12.5, ADR-0030).
        line += f" (Al leerla completa: {note.reading_notes[:CLASSIFY_READING_NOTES_CHARS]})"
    return line


def to_labels(
    out: ClassificationOut, request: ClassificationRequest
) -> tuple[ClassificationLabel, ...]:
    """Las etiquetas de la respuesta, solo de notas que estaban en el lote.

    Args:
        out: Respuesta validada.
        request: Lote enviado.

    Returns:
        Una etiqueta por nota del lote que la IA respondió (sin repetir).
    """
    wanted = {n.article_id for n in request.notes}
    seen: set[int] = set()
    labels: list[ClassificationLabel] = []
    for item in out.items:
        if item.id in wanted and item.id not in seen:
            seen.add(item.id)
            labels.append(
                ClassificationLabel(
                    item.id, item.category, item.label, parse_authority(item.authority)
                )
            )
    return tuple(labels)
