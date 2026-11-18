"""Proponer las frases de un concepto «como en Google» con la IA (ADR-0109).

El analista escribe en sus palabras lo que busca. ``SuggestConceptTerms``:

1. valida la descripción (``validated_intent``);
2. le pide a la IA nombre, frases tipo titular, exclusiones y los nombres
   propios que escribió la persona (``terms_v3``, ADR-0113);
3. deja solo los nombres propios que están tal cual en el texto
   (``literal_entities``) y que no son el lugar que nombró
   (``without_places``), y limpia las frases con las reglas del concepto
   (``clean_suggestion``): sin un nombre propio, la frase no sirve;
4. deja en la bitácora quién la pidió, qué escribió, qué se propuso y
   cuánto costó (``concept.terms_suggested``), aunque la IA falle.

Lo usan ``POST /api/v1/concepts/suggest`` (la propuesta llena el formulario y
el analista la revisa antes de guardar) y la búsqueda rápida.

No hace: no guarda el concepto ni busca noticias.
"""

from dataclasses import dataclass

from app.application.audit import CONCEPT_TERMS_SUGGESTED, Actor, AuditEntry
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.llm import (
    TermSuggesterPort,
    TermSuggestionError,
    TermSuggestionRequest,
    TermSuggestionResult,
)
from app.application.use_cases.reports import LLMPrices
from app.domain.concept import OPEN_MAX_PHRASES, QueryMode
from app.domain.enrichment import LLMUsage
from app.domain.errors import ProviderError, ServiceUnavailableError
from app.domain.term_suggestions import (
    MAX_SUGGESTED_EXCLUSIONS,
    EmptySuggestionError,
    SuggestedTerms,
    clean_suggestion,
    literal_entities,
    validated_intent,
    without_places,
)

# Lo que se muestra del costo: 0.000123 USD se lee mejor que 1.23e-04.
COST_DECIMALS = 6


def _clean_place(value: str | None) -> str | None:
    """Un lugar sin espacios de más, o ``None`` si viene vacío."""
    clean = " ".join((value or "").split())
    return clean or None


class TermSuggestionFailedError(ServiceUnavailableError):
    """La IA no respondió o no dio una propuesta válida."""

    code = "term_suggestion_failed"


@dataclass(frozen=True, slots=True)
class TermProposal:
    """Propuesta lista para el formulario.

    Attributes:
        terms: Nombre, frases, exclusiones y nombres propios ya limpios.
        query_mode: Siempre «como en Google»: las frases se pensaron para eso.
        model: Modelo que las propuso.
        cost_usd: Lo que costó la propuesta.
        place: Lugar que nombró el analista («Jalisco»), o ``None``; lo usa
            la búsqueda rápida (ADR-0110).
        place_state: Estado de ese lugar si es un municipio o ciudad.
        raw: Lo que respondió la IA, antes de limpiar. La búsqueda rápida
            vuelve a limpiar las frases si una entidad resulta ser el lugar
            del catálogo (un alias como «CDMX», ``without_places``).
    """

    terms: SuggestedTerms
    query_mode: QueryMode
    model: str
    cost_usd: float
    place: str | None = None
    place_state: str | None = None
    raw: TermSuggestionResult | None = None


class SuggestConceptTerms:
    """Caso de uso: la IA propone las frases de un concepto."""

    def __init__(
        self,
        suggester: TermSuggesterPort,
        prices: LLMPrices,
        concepts: ConceptRepositoryPort,
    ) -> None:
        """Recibe la IA, sus precios y dónde queda la bitácora.

        Args:
            suggester: La IA (``LLM_PROVIDER``).
            prices: Precios por millón de tokens, para el costo.
            concepts: Repositorio de conceptos (escribe la bitácora).
        """
        self._suggester = suggester
        self._prices = prices
        self._concepts = concepts

    def _cost(self, usage: LLMUsage) -> float:
        cost = usage.cost_usd(self._prices.input_per_million, self._prices.output_per_million)
        return round(cost, COST_DECIMALS)

    async def _record(
        self,
        actor: Actor,
        intent: str,
        usage: LLMUsage,
        details: dict[str, object],
    ) -> None:
        payload: dict[str, object] = {
            "descripcion": intent,
            "modelo": self._suggester.model,
            "prompt": self._suggester.terms_prompt_version,
            "tokens_entrada": usage.tokens_in,
            "tokens_salida": usage.tokens_out,
            "costo_usd": self._cost(usage),
        }
        await self._concepts.record_suggestion(
            AuditEntry(actor, CONCEPT_TERMS_SUGGESTED, payload | details)
        )

    async def execute(
        self, description: str, actor: Actor, *, require_phrases: bool = True, quick: bool = False
    ) -> TermProposal:
        """Pide la propuesta y la limpia.

        Args:
            description: Lo que busca el analista, en sus palabras.
            actor: Quién la pide (para la bitácora).
            require_phrases: ``False`` en la búsqueda rápida: si ninguna frase
                de la IA sirve, se busca el texto literal (ADR-0113).
            quick: ``True`` en la búsqueda rápida: basta un nombre («Pemex»)
                (``validated_intent``, revisión del 18/11/2026).

        Returns:
            La propuesta limpia con su costo.

        Raises:
            ConceptValidationError: Si la descripción es muy corta o muy larga.
            TermSuggestionFailedError: Si la IA no respondió o respondió mal.
            EmptySuggestionError: Si no quedó ninguna frase que se pueda buscar
                y ``require_phrases`` es ``True``.
        """
        intent = validated_intent(description, quick=quick)
        request = TermSuggestionRequest(intent, OPEN_MAX_PHRASES, MAX_SUGGESTED_EXCLUSIONS)
        try:
            result: TermSuggestionResult = await self._suggester.suggest_terms(request)
        except TermSuggestionError as error:
            await self._record(actor, intent, error.usage, {"error": str(error)})
            raise TermSuggestionFailedError(
                "La IA no dio una propuesta válida. Intenta de nuevo o escribe las frases a mano."
            ) from error
        except ProviderError as error:
            raise TermSuggestionFailedError(
                "La IA no respondió. Intenta de nuevo en un momento.",
                {"detalle": error.message},
            ) from error
        # Revisión del 18/11/2026 (hallazgo 3): el lugar no es nombre propio;
        # ya va aparte, en la región de la búsqueda.
        entities = without_places(
            literal_entities(intent, result.entities), (result.place, result.place_state)
        )
        try:
            terms = clean_suggestion(
                result.name,
                result.phrases,
                result.exclude_terms,
                entities=entities,
                require_phrases=require_phrases,
            )
        except EmptySuggestionError:
            # Sin frases útiles también se pagó: queda en la bitácora.
            await self._record(actor, intent, result.usage, {"error": "sin frases útiles"})
            raise
        place = _clean_place(result.place)
        details: dict[str, object] = {
            "frases": list(terms.phrases),
            "exclusiones": list(terms.exclude_terms),
        }
        if terms.entities:
            details["entidades"] = list(terms.entities)
        if place is not None:
            details["lugar"] = place
        await self._record(actor, intent, result.usage, details)
        return TermProposal(
            terms,
            QueryMode.OPEN,
            result.model,
            self._cost(result.usage),
            place,
            _clean_place(result.place_state),
            result,
        )
