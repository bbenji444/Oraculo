"""Reglas de los vínculos entre entidades de un caso (Fase 9.5; ADR-0104 y 0105).

Un vínculo une dos entidades ("aparecen juntas", "familiar", "es dueño de").
Hay dos orígenes en esta fase:

- **Coocurrencia (D6):** el sistema lo deriva solo cuando dos entidades
  confirmadas del caso aparecen en la misma nota. Nace sugerido y su
  confianza crece con las notas que comparten (``cooccurrence_confidence``).
- **Humano (D7):** lo dibuja el analista. No es una propuesta: nace
  confirmado con su firma y confianza 1.

Desde F12 (ADR-0107) cada vínculo también dice qué tan útil es para
investigar (``link_strength``): con tres notas casi todo «aparece junto» a
todo, pero pocas parejas **participan las dos en el mismo hecho** (la IA
marca en cada mención si la entidad participa o solo se nombra).

Quién lo usa: los casos de uso de vínculos y el repositorio que los deriva.

No hace: no guarda nada ni decide permisos; no propone vínculos con la IA
(el prompt ``entities_v1`` no los pide).
"""

from enum import StrEnum

from app.domain.concept import clean_text
from app.domain.errors import RelationshipValidationError
from app.domain.investigation import Origin, RelationshipType

# Confianza de un vínculo «aparecen juntas» según las notas del caso donde
# salen las dos entidades (decisión D6 del plan de la 9.5). Una nota puede
# nombrar a dos personas sin relación; tres ya es un patrón. Nunca llega a 1:
# esa es la de un vínculo que dibujó una persona.
COOCCURRENCE_CONFIDENCE: dict[int, float] = {1: 0.5, 2: 0.7}
COOCCURRENCE_CONFIDENCE_MAX = 0.9
# Lo que afirma una persona al crear un vínculo a mano (D7).
HUMAN_RELATIONSHIP_CONFIDENCE = 1.0
# Largo de la etiqueta propia ("socio en el salón") y de la nota de un
# vínculo: es un rótulo y un apunte breve, no un reporte. Decisión de la 9.5.
CUSTOM_LABEL_MAX_CHARS = 80
RELATIONSHIP_NOTES_MAX_CHARS = 1000


def cooccurrence_confidence(shared_articles: int) -> float:
    """Confianza de un vínculo «aparecen juntas» (decisión D6).

    Args:
        shared_articles: Notas del caso donde aparecen las dos entidades.

    Returns:
        0.5 con una nota, 0.7 con dos y 0.9 con tres o más.

    Raises:
        ValueError: Si no comparten ninguna nota (no hay vínculo).

    Example:
        >>> cooccurrence_confidence(2)
        0.7
    """
    if shared_articles < 1:
        raise ValueError("Sin notas compartidas no hay vínculo por coocurrencia.")
    return COOCCURRENCE_CONFIDENCE.get(shared_articles, COOCCURRENCE_CONFIDENCE_MAX)


def manual_relationship(
    kind: str, custom_label: str | None, notes: str | None
) -> tuple[RelationshipType, str | None, str | None]:
    """Valida lo que escribió el analista al crear un vínculo (D7).

    Args:
        kind: Tipo de vínculo (código de ``RelationshipType``).
        custom_label: Etiqueta propia; obligatoria solo en ``custom``.
        notes: Nota opcional del analista.

    Returns:
        El tipo, la etiqueta y la nota limpios (sin espacios de más; vacío
        se vuelve ``None``).

    Raises:
        RelationshipValidationError: Si el tipo no existe, si ``custom`` no
            trae etiqueta o si otro tipo sí la trae, o si algo es muy largo.

    Example:
        >>> manual_relationship("custom", "  socio en el salón ", None)
        (<RelationshipType.CUSTOM: 'custom'>, 'socio en el salón', None)
    """
    try:
        relationship = RelationshipType(kind)
    except ValueError as error:
        raise RelationshipValidationError(
            "Ese tipo de vínculo no existe.", {"type": kind}
        ) from error
    label = clean_text(custom_label or "") or None
    note = clean_text(notes or "") or None
    if relationship is RelationshipType.CUSTOM and label is None:
        raise RelationshipValidationError("Un vínculo «otro» necesita su etiqueta.", {})
    if relationship is not RelationshipType.CUSTOM and label is not None:
        raise RelationshipValidationError(
            "Solo un vínculo «otro» lleva etiqueta propia.", {"type": kind}
        )
    if label is not None and len(label) > CUSTOM_LABEL_MAX_CHARS:
        raise RelationshipValidationError(
            f"La etiqueta admite hasta {CUSTOM_LABEL_MAX_CHARS} caracteres.", {}
        )
    if note is not None and len(note) > RELATIONSHIP_NOTES_MAX_CHARS:
        raise RelationshipValidationError(
            f"La nota admite hasta {RELATIONSHIP_NOTES_MAX_CHARS} caracteres.", {}
        )
    return relationship, label, note


class LinkStrength(StrEnum):
    """Qué tan útil es un vínculo para investigar (F12, ADR-0107).

    No se guarda: se calcula al leer con la evidencia del momento.
    """

    # Las dos participan en el mismo hecho en al menos una nota, o lo afirmó
    # una persona al dibujarlo.
    STRONG = "strong"
    # Solo se nombran en la misma nota (una lista de dependencias, una
    # declaración de un funcionario...): se conserva, pero va al final.
    WEAK = "weak"


LINK_STRENGTH_LABEL: dict[LinkStrength, str] = {
    LinkStrength.STRONG: "relación fuerte",
    LinkStrength.WEAK: "solo se mencionan juntas",
}


def link_strength(origin: Origin, same_event_articles: int) -> LinkStrength:
    """Clasifica un vínculo para ordenarlo y agruparlo (F12, ADR-0107).

    Args:
        origin: Quién lo propuso.
        same_event_articles: Notas del caso donde las dos entidades participan
            en el hecho (rol ``event`` en las dos).

    Returns:
        ``STRONG`` si participan juntas en algún hecho o si lo dibujó una
        persona; ``WEAK`` si solo se nombran en las mismas notas.

    Example:
        >>> link_strength(Origin.COOCCURRENCE, 0)
        <LinkStrength.WEAK: 'weak'>
    """
    if same_event_articles > 0 or origin is Origin.HUMAN:
        return LinkStrength.STRONG
    return LinkStrength.WEAK


def _notes(count: int) -> str:
    return f"{count} {'nota' if count == 1 else 'notas'}"


def link_reason(origin: Origin, same_event_articles: int, shared_articles: int) -> str:
    """Por qué se relacionan dos entidades, en una frase para el analista.

    Args:
        origin: Quién propuso el vínculo.
        same_event_articles: Notas donde las dos participan en el hecho.
        shared_articles: Notas del caso donde aparecen las dos.

    Returns:
        La frase que acompaña al vínculo en la pantalla.

    Example:
        >>> link_reason(Origin.COOCCURRENCE, 2, 3)
        'participan en el mismo hecho en 2 notas (aparecen juntas en 3)'
    """
    if same_event_articles > 0:
        reason = f"participan en el mismo hecho en {_notes(same_event_articles)}"
        if shared_articles > same_event_articles:
            reason += f" (aparecen juntas en {shared_articles})"
        return reason
    if origin is Origin.HUMAN:
        return "lo afirmó una persona"
    if shared_articles > 0:
        return f"solo se mencionan juntas en {_notes(shared_articles)}"
    return "sin notas en común"
