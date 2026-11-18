"""Frases que la IA propone para un concepto «como en Google» (ADR-0109).

El analista escribe en sus palabras lo que busca («hackeos a bases de datos
del gobierno»). La IA propone un nombre, frases cortas escritas como titular
(«filtran datos», «hackeo gobierno») y exclusiones. Aquí vive lo que se hace
con esa propuesta antes de mostrarla:

- la descripción se valida con los mismos largos que la del concepto;
- cada frase y exclusión pasa por las reglas de una palabra clave
  (``is_searchable_term``); la que no las cumple se descarta en silencio,
  porque la persona solo ve la lista final y la puede editar;
- sin repetidas (sin mayúsculas ni acentos), hasta ``OPEN_MAX_PHRASES``
  frases y ``MAX_SUGGESTED_EXCLUSIONS`` exclusiones;
- una exclusión igual a una frase se quita: se anularían.

No hace: no llama a la IA ni guarda nada; el analista decide al guardar.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.concept import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    OPEN_MAX_PHRASES,
    clean_text,
    is_searchable_term,
)
from app.domain.errors import ConceptValidationError, InvalidRequestError
from app.domain.names import normalize_name

# Menos que esto no alcanza para saber qué se busca («robo» a secas): la IA
# inventaría el resto.
INTENT_MIN_LENGTH = 10
# Pocas: cada exclusión puede tirar una nota buena; la IA propone solo las
# que traen basura segura (cursos, publicidad).
MAX_SUGGESTED_EXCLUSIONS = 6
DESCRIPTION_FIELD = "description"


class EmptySuggestionError(InvalidRequestError):
    """La IA no propuso ninguna frase que se pueda buscar."""

    code = "empty_suggestion"


@dataclass(frozen=True, slots=True)
class SuggestedTerms:
    """Propuesta ya limpia, lista para llenar el formulario.

    Attributes:
        name: Nombre propuesto para el concepto, o ``""`` si no sirvió.
        phrases: Frases tipo titular (de 1 a ``OPEN_MAX_PHRASES``).
        exclude_terms: Exclusiones (hasta ``MAX_SUGGESTED_EXCLUSIONS``).
    """

    name: str
    phrases: tuple[str, ...]
    exclude_terms: tuple[str, ...]


def validated_intent(description: str) -> str:
    """Limpia y valida lo que el analista escribió.

    Args:
        description: Lo que busca, en sus palabras.

    Returns:
        El texto sin espacios repetidos.

    Raises:
        ConceptValidationError: Si es muy corto o muy largo, con el campo
            ``description`` como en el formulario.
    """
    intent = clean_text(description)
    if not INTENT_MIN_LENGTH <= len(intent) <= DESCRIPTION_MAX_LENGTH:
        raise ConceptValidationError(
            "Describe en tus palabras lo que buscas para que la IA proponga las frases.",
            {
                "problemas": [
                    {
                        "campo": DESCRIPTION_FIELD,
                        "mensaje": (
                            f"Escribe entre {INTENT_MIN_LENGTH} y {DESCRIPTION_MAX_LENGTH} "
                            "caracteres; por ejemplo «hackeos a bases de datos del gobierno»."
                        ),
                    }
                ]
            },
        )
    return intent


def _unique_terms(raw: Iterable[str], limit: int, taken: set[str]) -> tuple[str, ...]:
    """Términos válidos y sin repetir, en orden, hasta ``limit``."""
    kept: list[str] = []
    for value in raw:
        term = clean_text(value)
        norm = normalize_name(term)
        if not term or norm in taken or not is_searchable_term(term):
            continue
        taken.add(norm)
        kept.append(term)
        if len(kept) == limit:
            break
    return tuple(kept)


def clean_suggestion(
    name: str, phrases: Iterable[str], exclude_terms: Iterable[str]
) -> SuggestedTerms:
    """Aplica las reglas del concepto a lo que respondió la IA.

    Args:
        name: Nombre que propuso.
        phrases: Frases que propuso, en su orden (las primeras son las mejores).
        exclude_terms: Exclusiones que propuso.

    Returns:
        La propuesta limpia.

    Raises:
        EmptySuggestionError: Si no quedó ninguna frase que se pueda buscar.

    Example:
        >>> clean_suggestion("Hackeos", ["filtran datos", "Filtran datos", "a OR b"], ["curso"])
        SuggestedTerms(name='Hackeos', phrases=('filtran datos',), exclude_terms=('curso',))
    """
    taken: set[str] = set()
    kept_phrases = _unique_terms(phrases, OPEN_MAX_PHRASES, taken)
    if not kept_phrases:
        raise EmptySuggestionError(
            "La IA no propuso frases que se puedan buscar. Escríbelo con otras palabras "
            "o agrega las frases a mano."
        )
    kept_exclusions = _unique_terms(exclude_terms, MAX_SUGGESTED_EXCLUSIONS, taken)
    clean_name = clean_text(name)
    if not NAME_MIN_LENGTH <= len(clean_name) <= NAME_MAX_LENGTH:
        clean_name = ""
    return SuggestedTerms(clean_name, kept_phrases, kept_exclusions)
