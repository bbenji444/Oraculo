"""Frases de un concepto con la IA simulada: sin red ni gasto (ADR-0109).

Las respuestas tienen la forma documentada de cada proveedor (``/v1/responses``
de OpenAI y el SDK de Gemini), igual que las demás pruebas de la IA.
"""

import json
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from app.adapters.llm.common import TERMS_PROMPT_VERSION, TermsOut, build_terms_prompt
from app.adapters.llm.factory import MissingLLMKeyError, build_term_suggester
from app.adapters.llm.gemini import GeminiEnricher
from app.adapters.llm.openai import TERMS_SCHEMA, OpenAIEnricher
from app.application.ports.llm import TermSuggestionError, TermSuggestionRequest
from app.domain.enrichment import LLMUsage
from tests.unit.test_gemini import FakeModels, reply
from tests.unit.test_openai_llm import api_reply, enricher, settings

pytestmark = pytest.mark.anyio

REQUEST = TermSuggestionRequest("hackeos y filtraciones de bases de datos del gobierno", 12, 6)
VALID = {
    "name": "Hackeos a gobierno",
    "phrases": ["filtran datos", "hackeo gobierno", "ciberataque dependencia"],
    "exclude_terms": ["curso"],
}


def test_el_prompt_lleva_lo_que_busca_la_persona_y_los_topes() -> None:
    prompt = build_terms_prompt(REQUEST)

    assert prompt.rstrip().endswith(REQUEST.intent)
    assert "de 8 a 12 frases" in prompt
    assert "de 0 a 6 palabras" in prompt
    # Lo medido que explica por qué titulares y no catálogo.
    assert "«roban auto Jalisco» trae 19 notas" in prompt
    assert "NO pongas lugares" in prompt


def test_el_esquema_estricto_pide_todos_los_campos() -> None:
    assert set(TERMS_SCHEMA["required"]) == set(TERMS_SCHEMA["properties"])
    assert TERMS_SCHEMA["additionalProperties"] is False


async def test_openai_propone_con_su_esquema_estricto() -> None:
    seen: list[dict[str, Any]] = []
    llm = enricher(httpx2.Response(200, json=api_reply(json.dumps(VALID), 400, 90)), seen=seen)

    result = await llm.suggest_terms(REQUEST)

    assert result.name == "Hackeos a gobierno"
    assert result.phrases == ("filtran datos", "hackeo gobierno", "ciberataque dependencia")
    assert result.exclude_terms == ("curso",)
    assert (result.usage, result.model, result.prompt_version) == (
        LLMUsage(400, 90),
        "gpt-6-luna",
        TERMS_PROMPT_VERSION,
    )
    assert llm.terms_prompt_version == TERMS_PROMPT_VERSION
    body = seen[0]["body"]
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "terms",
        "schema": TERMS_SCHEMA,
        "strict": True,
    }
    assert body["input"][0]["content"] == build_terms_prompt(REQUEST)
    await llm.aclose()


async def test_openai_dos_respuestas_invalidas_son_error_con_lo_gastado() -> None:
    llm = enricher(
        httpx2.Response(200, json=api_reply("no es json", 400, 5)),
        httpx2.Response(200, json=api_reply('{"frases": []}', 400, 5)),
        seen=[],
    )

    with pytest.raises(TermSuggestionError, match="OpenAI") as error:
        await llm.suggest_terms(REQUEST)

    assert error.value.usage == LLMUsage(800, 10)
    await llm.aclose()


async def test_gemini_propone_con_el_mismo_prompt_y_esquema() -> None:
    models = FakeModels(reply(VALID, 380, 80))
    llm = GeminiEnricher(models, "gemini-2.5-flash")

    result = await llm.suggest_terms(REQUEST)

    assert result.phrases[0] == "filtran datos"
    assert (result.usage, result.prompt_version) == (LLMUsage(380, 80), TERMS_PROMPT_VERSION)
    assert llm.terms_prompt_version == TERMS_PROMPT_VERSION
    call = models.calls[0]
    assert call["contents"] == build_terms_prompt(REQUEST)
    assert call["config"].response_schema is TermsOut


async def test_gemini_respuesta_invalida_es_error_con_lo_gastado() -> None:
    llm = GeminiEnricher(FakeModels(reply("[]", 300, 3), reply("{}", 300, 3)), "gemini-2.5-flash")

    with pytest.raises(TermSuggestionError, match="Gemini") as error:
        await llm.suggest_terms(REQUEST)

    assert error.value.usage == LLMUsage(600, 6)


def test_la_fabrica_de_frases_usa_la_ia_elegida_y_sus_precios() -> None:
    openai = build_term_suggester(settings(openai_api_key=SecretStr("x")))
    gemini = build_term_suggester(settings(llm_provider="gemini", gemini_api_key=SecretStr("y")))

    assert (openai.provider, openai.price_input_per_million) == ("openai", 0.10)
    assert isinstance(openai.suggester, OpenAIEnricher)
    assert (gemini.provider, gemini.price_output_per_million) == ("gemini", 2.50)
    assert isinstance(gemini.suggester, GeminiEnricher)
    with pytest.raises(MissingLLMKeyError):
        build_term_suggester(settings())
