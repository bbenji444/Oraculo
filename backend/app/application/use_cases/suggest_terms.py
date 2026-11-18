"""Proponer las frases de un concepto «como en Google» con la IA (ADR-0109).

El analista escribe en sus palabras lo que busca. ``SuggestConceptTerms``:

1. valida la descripción (``validated_intent``);
2. le pide a la IA nombre, frases tipo titular y exclusiones;
3. las limpia con las reglas del concepto (``clean_suggestion``);
4. deja en la bitácora quién la pidió, qué escribió, qué se propuso y
   cuánto costó (``concept.terms_suggested``), aunque la IA falle.

Lo usa ``POST /api/v1/concepts/suggest``: la propuesta llena el formulario y
el analista la revisa antes de guardar.

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
    validated_intent,
)

# Lo que se muestra del costo: 0.000123 USD se lee mejor que 1.23e-04.
COST_DECIMALS = 6


class TermSuggestionFailedError(ServiceUnavailableError):
    """La IA no respondió o no dio una propuesta válida."""

    code = "term_suggestion_failed"


@dataclass(frozen=True, slots=True)
class TermProposal:
    """Propuesta lista para el formulario.

    Attributes:
        terms: Nombre, frases y exclusiones ya limpios.
        query_mode: Siempre «como en Google»: las frases se pensaron para eso.
        model: Modelo que las propuso.
        cost_usd: Lo que costó la propuesta.
    """

    terms: SuggestedTerms
    query_mode: QueryMode
    model: str
    cost_usd: float


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
        terms: SuggestedTerms | None,
        error: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "descripcion": intent,
            "modelo": self._suggester.model,
            "prompt": self._suggester.terms_prompt_version,
            "tokens_entrada": usage.tokens_in,
            "tokens_salida": usage.tokens_out,
            "costo_usd": self._cost(usage),
        }
        if terms is not None:
            payload |= {"frases": list(terms.phrases), "exclusiones": list(terms.exclude_terms)}
        if error is not None:
            payload["error"] = error
        await self._concepts.record_suggestion(AuditEntry(actor, CONCEPT_TERMS_SUGGESTED, payload))

    async def execute(self, description: str, actor: Actor) -> TermProposal:
        """Pide la propuesta y la limpia.

        Args:
            description: Lo que busca el analista, en sus palabras.
            actor: Quién la pide (para la bitácora).

        Returns:
            La propuesta limpia con su costo.

        Raises:
            ConceptValidationError: Si la descripción es muy corta o muy larga.
            TermSuggestionFailedError: Si la IA no respondió o respondió mal.
            EmptySuggestionError: Si no quedó ninguna frase que se pueda buscar.
        """
        intent = validated_intent(description)
        request = TermSuggestionRequest(intent, OPEN_MAX_PHRASES, MAX_SUGGESTED_EXCLUSIONS)
        try:
            result: TermSuggestionResult = await self._suggester.suggest_terms(request)
        except TermSuggestionError as error:
            await self._record(actor, intent, error.usage, None, str(error))
            raise TermSuggestionFailedError(
                "La IA no dio una propuesta válida. Intenta de nuevo o escribe las frases a mano."
            ) from error
        except ProviderError as error:
            raise TermSuggestionFailedError(
                "La IA no respondió. Intenta de nuevo en un momento.",
                {"detalle": error.message},
            ) from error
        try:
            terms = clean_suggestion(result.name, result.phrases, result.exclude_terms)
        except EmptySuggestionError:
            # Sin frases útiles también se pagó: queda en la bitácora.
            await self._record(actor, intent, result.usage, None, "sin frases útiles")
            raise
        await self._record(actor, intent, result.usage, terms)
        return TermProposal(terms, QueryMode.OPEN, result.model, self._cost(result.usage))
