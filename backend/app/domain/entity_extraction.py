"""Entidades que la IA propone de una nota y el freno contra lo inventado (Fase 9.4).

Cuando una noticia entra a un caso, la IA lee su texto y propone personas,
organizaciones, lugares y vehículos, cada uno con una cita de la nota
(``evidence_span``). Este módulo decide **qué propuestas se aceptan como
sugerencia**:

- **Solo lo que dice el texto (ADR-0105):** la cita debe aparecer literal en
  lo que leyó la IA (sin distinguir mayúsculas, espacios repetidos ni comillas
  tipográficas), y el nombre o uno de sus alias también. Lo demás se descarta
  y se cuenta, con su motivo (``Rejection``).
- **Estatus legal:** solo personas y solo los códigos de ``LegalStatus``. No
  existe "culpable"; un valor desconocido queda vacío.
- **Cita corta:** máximo ``EVIDENCE_SPAN_MAX_CHARS``; si la IA da más, se
  recorta alrededor del nombre.

También tiene las reglas puras que usan los casos de uso: de dónde sale el
texto (``analyzed_text``), qué estatus legal se sugiere al confirmar
(``suggested_legal_status``), qué lugar del catálogo corresponde a una entidad
lugar (``match_region``) y qué se exige al confirmar
(``confirmed_legal_status``).

No hace: no llama a la IA, no guarda nada y no junta entidades de notas
distintas (eso lo hace el repositorio dentro de un caso, decisión D6).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.concept import clean_text
from app.domain.enrichment import LLMUsage, text_for_llm
from app.domain.entity_resolution import entity_name_norm
from app.domain.errors import EntityReviewError
from app.domain.geocoding import MentionRole
from app.domain.investigation import (
    EVIDENCE_SPAN_MAX_CHARS,
    LEGAL_STATUS_LABEL,
    EntityType,
    LegalStatus,
)
from app.domain.names import normalize_name

# Decisión D2 de la 9.4: tope de notas que se analizan por caso. Un caso real
# ("Homicidio estilista Polanco") tiene 8; el tope solo frena un caso
# desbocado (200 notas ≈ 0.13 USD con gpt-6-luna).
CASE_EXTRACTION_MAX_ARTICLES = 200
# Alias que se guardan por propuesta: los apodos reales son pocos ("Eduardo
# N", "Micky Hair"); más suele ser la IA repitiendo variantes.
MAX_ALIASES = 5
# Tokens que se suponen por nota para estimar ANTES de gastar: el prompt
# entities_v1 (~900), el texto recortado (~1,500) y una respuesta con unas
# 10 entidades y sus citas (~800). El costo real se registra con lo que
# reporta la IA; se ajusta con la medición del punto de control de la 9.4.
ESTIMATED_TOKENS_IN_PER_EXTRACTION = 2500
ESTIMATED_TOKENS_OUT_PER_EXTRACTION = 800

# Tipos que se le piden a la IA (plan §9.7). Cuentas y teléfonos existen en el
# modelo para capturarlos a mano más adelante, pero no se extraen de notas.
EXTRACTABLE_TYPES = frozenset(
    {EntityType.PERSON, EntityType.ORG, EntityType.PLACE, EntityType.VEHICLE}
)

# Comillas y guiones tipográficos: la IA suele cambiar unos por otros al
# citar, y no por eso la cita deja de ser literal.
_TYPOGRAPHY = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "«": '"',
        "»": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
    }
)
# Lo que se quita de los extremos de una cita antes de buscarla: espacios,
# puntos suspensivos y el punto final que la IA agrega o quita. Las comillas
# solo si envuelven toda la cita: las de en medio son parte del texto.
_QUOTE_EDGES = " \t\r\n…."
_QUOTES = frozenset("\"'“”«»‘’„")
# Una comilla de cada lado.
_WRAPPED_MIN_LENGTH = 2


class CaseArticleEntitiesStatus(StrEnum):
    """Columna ``case_articles.entities_status``: en qué va cada nota del caso."""

    PENDING = "pending"
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExtractionState(StrEnum):
    """Columna ``entity_extractions.status``."""

    OK = "ok"
    FAILED = "failed"


class TextSource(StrEnum):
    """Columna ``entity_extractions.source``: qué texto leyó la IA (decisión D9)."""

    FULL_TEXT = "full_text"
    TITLE_SNIPPET = "title_snippet"


class RejectionReason(StrEnum):
    """Por qué una propuesta de la IA no quedó como sugerencia."""

    UNSUPPORTED_TYPE = "unsupported_type"
    BLANK_LABEL = "blank_label"
    EVIDENCE_NOT_IN_TEXT = "evidence_not_in_text"
    NAME_NOT_IN_TEXT = "name_not_in_text"
    DUPLICATE = "duplicate"


REJECTION_LABEL: dict[RejectionReason, str] = {
    RejectionReason.UNSUPPORTED_TYPE: "tipo que no se extrae",
    RejectionReason.BLANK_LABEL: "sin nombre",
    RejectionReason.EVIDENCE_NOT_IN_TEXT: "la cita no está en la nota",
    RejectionReason.NAME_NOT_IN_TEXT: "el nombre no está en la nota",
    RejectionReason.DUPLICATE: "repetida",
}


@dataclass(frozen=True, slots=True)
class RawProposal:
    """Una entidad tal como la propuso la IA (ya con la forma del esquema).

    Attributes:
        type: Tipo ("person", "org", "place", "vehicle").
        label: Nombre como aparece en la nota.
        aliases: Otros nombres que la nota usa para la misma entidad.
        role: "event" si participa en el hecho; "mentioned" si solo se nombra.
        legal_status_hint: Código de ``LegalStatus`` según la nota, o ``None``.
        confidence: Confianza de la IA, de 0 a 1.
        evidence_span: Cita de la nota donde aparece.
    """

    type: str
    label: str
    aliases: tuple[str, ...]
    role: str
    legal_status_hint: str | None
    confidence: float
    evidence_span: str


@dataclass(frozen=True, slots=True)
class Proposal:
    """Una propuesta que pasó la revisión contra el texto: será una sugerencia.

    Attributes:
        type: Tipo de entidad.
        label: Nombre, tal como aparece en la nota.
        label_norm: Nombre normalizado (``entity_name_norm``: sin comillas) para agrupar.
        aliases: Otros nombres, todos presentes en la nota.
        role: Si participa en el hecho o solo se nombra.
        legal_status_hint: Lo que la nota dice de la persona, o ``None``.
        confidence: De 0 a 1.
        evidence_span: La cita, copiada del texto de la nota (no de la IA).
        char_start: Dónde empieza la cita en el cuerpo analizado, o ``None``
            si está en el título.
        char_end: Dónde termina, o ``None``.
    """

    type: EntityType
    label: str
    label_norm: str
    aliases: tuple[str, ...]
    role: MentionRole
    legal_status_hint: LegalStatus | None
    confidence: float
    evidence_span: str
    char_start: int | None
    char_end: int | None


@dataclass(frozen=True, slots=True)
class Rejection:
    """Una propuesta descartada, para medir a la IA (no se muestra como sugerencia).

    Attributes:
        type: Tipo que dio la IA.
        label: Nombre que dio la IA.
        reason: Motivo.
        evidence_span: La cita que dio la IA (recortada a la longitud máxima).
    """

    type: str
    label: str
    reason: RejectionReason
    evidence_span: str


@dataclass(frozen=True, slots=True)
class ReviewedProposals:
    """Resultado de revisar lo que propuso la IA para una nota.

    Attributes:
        proposals: Las que serán sugerencias.
        rejected: Las descartadas, con su motivo.
    """

    proposals: tuple[Proposal, ...]
    rejected: tuple[Rejection, ...]


@dataclass(frozen=True, slots=True)
class AnalyzedText:
    """El texto que lee la IA de una nota, y contra el que se revisan sus citas.

    Attributes:
        title: Título de la nota.
        body: Cuerpo recortado (``text_for_llm``), o el fragmento si el texto
            ya se borró.
        source: Si es el texto completo o solo título y fragmento (D9).
    """

    title: str
    body: str
    source: TextSource


def analyzed_text(
    title: str, stored_body: str | None, snippet: str | None, *, full_text: bool
) -> AnalyzedText:
    """Elige el texto que se le da a la IA (decisión D9).

    El resumen propio nunca se usa: lo escribió la IA y citarlo no prueba
    nada. Si el texto de la nota ya se borró (30 días, ADR-0015), quedan el
    título y el fragmento, que son del medio.

    Args:
        title: Título.
        stored_body: Texto guardado en ``article_texts``, si todavía existe.
        snippet: Fragmento del proveedor.
        full_text: Si el texto guardado es el cuerpo extraído
            (``extraction_status = ok``) y no título + fragmento.

    Returns:
        Título, cuerpo y de dónde salió.
    """
    if stored_body:
        source = TextSource.FULL_TEXT if full_text else TextSource.TITLE_SNIPPET
        return AnalyzedText(title, text_for_llm(stored_body), source)
    return AnalyzedText(title, snippet or "", TextSource.TITLE_SNIPPET)


def _fold(text: str) -> tuple[str, list[int]]:
    """Texto para comparar (minúsculas, un solo espacio) y de qué posición vino cada letra."""
    chars: list[str] = []
    origin: list[int] = []
    space_at: int | None = None
    for index, char in enumerate(text.translate(_TYPOGRAPHY)):
        if char.isspace():
            space_at = index if chars else None
            continue
        if space_at is not None:
            chars.append(" ")
            origin.append(space_at)
            space_at = None
        for folded in char.casefold():
            chars.append(folded)
            origin.append(index)
    return "".join(chars), origin


def _bare(quote: str) -> str:
    """La cita sin lo que la IA le agrega en los extremos."""
    core = quote.strip(_QUOTE_EDGES)
    if len(core) >= _WRAPPED_MIN_LENGTH and core[0] in _QUOTES and core[-1] in _QUOTES:
        core = core[1:-1].strip(_QUOTE_EDGES)
    return core


def _is_word_edge(text: str, index: int) -> bool:
    return index < 0 or index >= len(text) or not text[index].isalnum()


def find_quote(quote: str, text: str, *, whole_words: bool = False) -> tuple[int, int] | None:
    """Busca una cita en el texto sin distinguir mayúsculas, espacios ni comillas tipográficas.

    Args:
        quote: Lo que dice la IA que está en la nota.
        text: El texto donde se busca.
        whole_words: Si la cita debe empezar y terminar en límite de palabra
            (para nombres: "Ana" no debe encontrarse dentro de "Mariana").

    Returns:
        Posiciones de inicio y fin en ``text`` (para copiar la cita tal como
        está en la nota), o ``None`` si no aparece.

    Example:
        >>> find_quote("el ASESINATO del  estilista", "Tras el asesinato del estilista Miguel")
        (5, 31)
    """
    needle, _ = _fold(_bare(quote))
    if not needle:
        return None
    haystack, origin = _fold(text)
    at = haystack.find(needle)
    while at >= 0:
        end = at + len(needle)
        if not whole_words or (_is_word_edge(haystack, at - 1) and _is_word_edge(haystack, end)):
            return origin[at], origin[end - 1] + 1
        at = haystack.find(needle, at + 1)
    return None


def _in_text(name: str, text: AnalyzedText) -> bool:
    return any(
        find_quote(name, part, whole_words=True) is not None for part in (text.title, text.body)
    )


def legal_status_from(value: str | None) -> LegalStatus | None:
    """Traduce el estatus legal que dio la IA a un código válido.

    Acepta el código ("alleged") o su etiqueta en español ("señalado"), por si
    la IA responde en español. Cualquier otra cosa (incluido "culpable", que
    no existe a propósito) queda vacía.

    Args:
        value: Lo que dio la IA.

    Returns:
        El código, o ``None``.

    Example:
        >>> legal_status_from("Vinculado a proceso")
        <LegalStatus.CHARGED: 'charged'>
        >>> legal_status_from("culpable") is None
        True
    """
    if value is None:
        return None
    cleaned = clean_text(value).lower()
    try:
        return LegalStatus(cleaned)
    except ValueError:
        by_label = {normalize_name(label): code for code, label in LEGAL_STATUS_LABEL.items()}
        return by_label.get(normalize_name(cleaned))


def _entity_type(value: str) -> EntityType | None:
    try:
        kind = EntityType(value)
    except ValueError:
        return None
    return kind if kind in EXTRACTABLE_TYPES else None


def _trim_around(text: str, start: int, end: int, focus: tuple[int, int] | None) -> tuple[int, int]:
    """Recorta ``text[start:end]`` a la longitud máxima, sin perder el nombre ni cortar palabras."""
    if end - start <= EVIDENCE_SPAN_MAX_CHARS:
        return start, end
    focus_start, focus_end = focus or (start, start)
    window_start = max(start, min(focus_start, focus_end - EVIDENCE_SPAN_MAX_CHARS))
    window_end = window_start + EVIDENCE_SPAN_MAX_CHARS
    if window_start > start:
        # Empieza en la palabra siguiente, salvo que eso deje fuera el nombre.
        space = text.find(" ", window_start, focus_start)
        if space >= 0:
            window_start = space + 1
    space = text.rfind(" ", max(window_start, focus_end), window_end)
    if space > window_start:
        window_end = space
    return window_start, window_end


def _evidence(
    raw: RawProposal, names: Sequence[str], text: AnalyzedText
) -> tuple[str, int | None, int | None] | None:
    """La cita copiada de la nota (cuerpo primero, luego título), o ``None`` si no está."""
    for part, positions in ((text.body, True), (text.title, False)):
        found = find_quote(raw.evidence_span, part)
        if found is None:
            continue
        start, end = found
        focus: tuple[int, int] | None = None
        for name in names:
            inside = find_quote(name, part[start:end], whole_words=True)
            if inside is not None:
                focus = (start + inside[0], start + inside[1])
                break
        start, end = _trim_around(part, start, end, focus)
        cut = part[start:end]
        span = cut.strip()
        start += len(cut) - len(cut.lstrip())
        end = start + len(span)
        return (span, start, end) if positions else (span, None, None)
    return None


def _aliases(raw_aliases: Iterable[str], label_norm: str, text: AnalyzedText) -> list[str]:
    """Alias limpios, sin repetir, distintos del nombre y presentes en la nota."""
    kept: list[str] = []
    seen = {label_norm}
    for alias in raw_aliases:
        cleaned = clean_text(alias)
        norm = entity_name_norm(cleaned)
        if not norm or norm in seen or not _in_text(cleaned, text):
            continue
        seen.add(norm)
        kept.append(cleaned)
        if len(kept) == MAX_ALIASES:
            break
    return kept


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def review_proposals(raw: Sequence[RawProposal], text: AnalyzedText) -> ReviewedProposals:
    """Revisa lo que propuso la IA contra el texto que leyó (decisión D5).

    Una propuesta queda solo si su tipo se extrae, su cita aparece en la nota
    y su nombre (o uno de sus alias) también. Si el nombre no aparece pero un
    alias sí, el alias pasa a ser el nombre: lo que se muestra siempre está
    escrito en la nota. La cita que se guarda es la del texto, no la de la IA.

    Args:
        raw: Propuestas de la IA para una nota.
        text: El texto que leyó.

    Returns:
        Las propuestas aceptadas y las descartadas con su motivo.
    """
    kept: list[Proposal] = []
    rejected: list[Rejection] = []
    seen: set[tuple[EntityType, str, str]] = set()
    for item in raw:
        kind = _entity_type(item.type)
        label = clean_text(item.label)
        if kind is None:
            rejected.append(_rejection(item, RejectionReason.UNSUPPORTED_TYPE))
            continue
        if not entity_name_norm(label):
            rejected.append(_rejection(item, RejectionReason.BLANK_LABEL))
            continue
        aliases = _aliases(item.aliases, entity_name_norm(label), text)
        if not _in_text(label, text):
            if not aliases:
                rejected.append(_rejection(item, RejectionReason.NAME_NOT_IN_TEXT))
                continue
            label = aliases.pop(0)
        evidence = _evidence(item, [label, *aliases], text)
        if evidence is None:
            rejected.append(_rejection(item, RejectionReason.EVIDENCE_NOT_IN_TEXT))
            continue
        span, start, end = evidence
        key = (kind, entity_name_norm(label), span)
        if key in seen:
            rejected.append(_rejection(item, RejectionReason.DUPLICATE))
            continue
        seen.add(key)
        kept.append(
            Proposal(
                type=kind,
                label=label,
                label_norm=entity_name_norm(label),
                aliases=tuple(aliases),
                role=MentionRole.EVENT if item.role == MentionRole.EVENT else MentionRole.MENTIONED,
                legal_status_hint=(
                    legal_status_from(item.legal_status_hint) if kind is EntityType.PERSON else None
                ),
                confidence=_clamp(item.confidence),
                evidence_span=span,
                char_start=start,
                char_end=end,
            )
        )
    return ReviewedProposals(tuple(kept), tuple(rejected))


def _rejection(item: RawProposal, reason: RejectionReason) -> Rejection:
    return Rejection(
        item.type, clean_text(item.label), reason, item.evidence_span[:EVIDENCE_SPAN_MAX_CHARS]
    )


@dataclass(frozen=True, slots=True)
class MentionHint:
    """Lo que dice una mención del estatus legal de una persona, y cuándo.

    Attributes:
        published_at: Fecha de la nota de la mención, si se conoce.
        mention_id: Id de la mención (desempata: la más nueva gana).
        legal_status: Estatus que sugirió la IA en esa nota, o ``None``.
    """

    published_at: datetime | None
    mention_id: int
    legal_status: LegalStatus | None


def suggested_legal_status(hints: Iterable[MentionHint]) -> LegalStatus | None:
    """Estatus legal que se propone al confirmar: el de la nota más reciente que lo dice.

    Las notas avanzan ("señalado" → "detenido" → "vinculado a proceso"); la
    persona que confirma lo acepta o lo cambia (decisión D7).

    Args:
        hints: Menciones de la entidad en el caso.

    Returns:
        El estatus de la nota más reciente que dice alguno, o ``None``.
    """
    known = [h for h in hints if h.legal_status is not None]
    if not known:
        return None
    latest = max(
        known,
        key=lambda h: (
            h.published_at is not None,
            h.published_at.timestamp() if h.published_at else 0.0,
            h.mention_id,
        ),
    )
    return latest.legal_status


def match_region(names: Iterable[str], locations: Iterable[tuple[str, int | None]]) -> int | None:
    """Región del catálogo para una entidad lugar, con lo que ya se ubicó de la nota (D8).

    El punto de un lugar nunca sale de la IA (§11): si el geolocalizador ya
    resolvió una mención con el mismo nombre en la misma nota, se usa esa
    región.

    Args:
        names: Nombre y alias de la entidad, ya normalizados.
        locations: Menciones de lugar de la nota (texto y región resuelta).

    Returns:
        El id de la región, o ``None`` si ninguna mención resuelta coincide.
    """
    wanted = set(names)
    return next(
        (
            region_id
            for mention, region_id in locations
            if region_id is not None and entity_name_norm(mention) in wanted
        ),
        None,
    )


def confirmed_legal_status(kind: EntityType, value: str | None) -> LegalStatus | None:
    """Valida el estatus legal con el que una persona confirma una entidad (D7, ADR-0105).

    Args:
        kind: Tipo de la entidad.
        value: Estatus elegido.

    Returns:
        El estatus de una persona, o ``None`` si no es persona.

    Raises:
        EntityReviewError: Si es persona y no trae estatus (o trae uno que no
            existe), o si no es persona y trae estatus.
    """
    if kind is not EntityType.PERSON:
        if value is not None:
            raise EntityReviewError("Solo las personas llevan estatus legal.", {"type": kind.value})
        return None
    if value is None:
        raise EntityReviewError(
            "Para confirmar a una persona elige su estatus legal según la nota "
            "(si no dice nada, «mencionado»)."
        )
    try:
        return LegalStatus(value)
    except ValueError as error:
        raise EntityReviewError(
            f"Estatus legal desconocido: «{value}».",
            {"permitidos": [status.value for status in LegalStatus]},
        ) from error


def estimated_extraction_usage(articles: int) -> LLMUsage:
    """Tokens que se calculan para analizar cierta cantidad de notas, antes de gastar.

    Args:
        articles: Notas que se mandarían a la IA.

    Returns:
        Tokens estimados.

    Example:
        >>> round(estimated_extraction_usage(8).cost_usd(0.10, 0.50), 4)
        0.0052
    """
    return LLMUsage(
        articles * ESTIMATED_TOKENS_IN_PER_EXTRACTION,
        articles * ESTIMATED_TOKENS_OUT_PER_EXTRACTION,
    )
