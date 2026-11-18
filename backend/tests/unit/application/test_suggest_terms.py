"""Propuesta de frases con la IA simulada: limpieza, costo y bitácora (ADR-0109)."""

from dataclasses import dataclass, field

import pytest

from app.application.audit import CONCEPT_TERMS_SUGGESTED, Actor
from app.application.ports.llm import (
    TermSuggestionError,
    TermSuggestionRequest,
    TermSuggestionResult,
)
from app.application.use_cases.reports import LLMPrices
from app.application.use_cases.suggest_terms import (
    SuggestConceptTerms,
    TermSuggestionFailedError,
)
from app.domain.concept import OPEN_MAX_PHRASES, QueryMode
from app.domain.enrichment import LLMUsage
from app.domain.errors import ConceptValidationError, ProviderError
from app.domain.term_suggestions import EmptySuggestionError
from tests.unit.fake_concepts import FakeConceptRepository

pytestmark = pytest.mark.anyio

ACTOR = Actor("benji", "10.0.0.1")
# 1 USD por millón de entrada y 4 de salida: el costo se lee directo.
PRICES = LLMPrices("openai", 1.0, 4.0)
INTENT = "hackeos y filtraciones de bases de datos del gobierno"


@dataclass
class FakeSuggester:
    """IA de mentira: devuelve lo que se le diga o falla."""

    result: TermSuggestionResult | None = None
    error: Exception | None = None
    requests: list[TermSuggestionRequest] = field(default_factory=list)

    @property
    def model(self) -> str:
        return "gpt-6-luna"

    @property
    def terms_prompt_version(self) -> str:
        return "terms_v1"

    async def aclose(self) -> None:
        return None

    async def suggest_terms(self, request: TermSuggestionRequest) -> TermSuggestionResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def result(*phrases: str, excludes: tuple[str, ...] = ("curso",)) -> TermSuggestionResult:
    return TermSuggestionResult(
        "Hackeos a gobierno", phrases, excludes, LLMUsage(1000, 250), "gpt-6-luna", "terms_v1"
    )


async def test_propone_frases_limpias_con_su_costo_y_bitacora() -> None:
    repo = FakeConceptRepository()
    suggester = FakeSuggester(
        result("filtran datos", "Filtran datos", '"hackeo"', "hackeo gobierno")
    )

    proposal = await SuggestConceptTerms(suggester, PRICES, repo).execute(f"  {INTENT} ", ACTOR)

    assert proposal.terms.phrases == ("filtran datos", "hackeo gobierno")
    assert proposal.terms.exclude_terms == ("curso",)
    assert proposal.query_mode is QueryMode.OPEN
    # 1000 x 1 + 250 x 4 = 2000 por millón.
    assert proposal.cost_usd == pytest.approx(0.002)
    [request] = suggester.requests
    assert (request.intent, request.max_phrases) == (INTENT, OPEN_MAX_PHRASES)
    [(entity_id, entry)] = repo.audit
    assert (entity_id, entry.action, entry.actor) == (0, CONCEPT_TERMS_SUGGESTED, ACTOR)
    assert entry.payload["descripcion"] == INTENT
    assert entry.payload["frases"] == ["filtran datos", "hackeo gobierno"]
    assert entry.payload["costo_usd"] == pytest.approx(0.002)
    assert entry.payload["prompt"] == "terms_v1"


async def test_descripcion_muy_corta_no_llama_a_la_ia() -> None:
    repo = FakeConceptRepository()
    suggester = FakeSuggester(result("filtran datos"))

    with pytest.raises(ConceptValidationError):
        await SuggestConceptTerms(suggester, PRICES, repo).execute("robo", ACTOR)

    assert suggester.requests == []
    assert repo.audit == []


async def test_respuesta_invalida_queda_en_la_bitacora_con_lo_gastado() -> None:
    repo = FakeConceptRepository()
    error = TermSuggestionError("JSON roto", LLMUsage(800, 10))
    suggester = FakeSuggester(error=error)

    with pytest.raises(TermSuggestionFailedError, match="a mano"):
        await SuggestConceptTerms(suggester, PRICES, repo).execute(INTENT, ACTOR)

    [(_, entry)] = repo.audit
    assert entry.payload["error"] == "JSON roto"
    assert entry.payload["tokens_entrada"] == 800


async def test_si_la_ia_no_responde_es_error_claro() -> None:
    suggester = FakeSuggester(error=ProviderError("Tiempo agotado", provider="openai"))

    with pytest.raises(TermSuggestionFailedError, match="no respondió"):
        await SuggestConceptTerms(suggester, PRICES, FakeConceptRepository()).execute(INTENT, ACTOR)


async def test_sin_frases_utiles_tambien_queda_en_la_bitacora() -> None:
    repo = FakeConceptRepository()
    suggester = FakeSuggester(result('"x"', "a OR b"))

    with pytest.raises(EmptySuggestionError):
        await SuggestConceptTerms(suggester, PRICES, repo).execute(INTENT, ACTOR)

    [(_, entry)] = repo.audit
    assert entry.payload["error"] == "sin frases útiles"
