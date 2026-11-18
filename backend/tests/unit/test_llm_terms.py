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
    # Sin lugar en la respuesta (o una de terms_v1): None.
    assert (result.place, result.place_state) == (None, None)
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
    models = FakeModels(reply(VALID | {"place": "Guadalajara", "place_state": "Jalisco"}, 380, 80))
    llm = GeminiEnricher(models, "gemini-2.5-flash")

    result = await llm.suggest_terms(REQUEST)

    assert result.phrases[0] == "filtran datos"
    assert (result.place, result.place_state) == ("Guadalajara", "Jalisco")
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


async def test_openai_devuelve_el_lugar_que_nombro_la_persona() -> None:
    answer = VALID | {"place": "Jalisco", "place_state": None}
    llm = enricher(httpx2.Response(200, json=api_reply(json.dumps(answer), 400, 90)), seen=[])

    result = await llm.suggest_terms(REQUEST)

    assert (result.place, result.place_state) == ("Jalisco", None)
    await llm.aclose()


def test_el_prompt_pide_el_lugar_y_su_estado() -> None:
    prompt = build_terms_prompt(REQUEST)

    assert "place:" in prompt
    assert "place_state:" in prompt
    assert '"Guadalajara" → "Jalisco"' in prompt


# --- terms_v3: nombres propios copiados tal cual (ADR-0113) ---


def test_el_prompt_v3_exige_copiar_los_nombres_propios_tal_cual() -> None:
    prompt = build_terms_prompt(TermSuggestionRequest("hacker eternal", 12, 6))

    assert TERMS_PROMPT_VERSION == "terms_v3"
    assert "Copia EXACTOS los nombres propios" in prompt
    assert '"hacker" no es "hackeo"' in prompt
    assert "TODAS las frases lo llevan" in prompt
    assert "Ponlos en entities" in prompt
    # El lugar que es parte de un nombre no es el lugar.
    assert "Cártel de Sinaloa" in prompt
    # Ejemplo resuelto con el caso de Benji.
    assert "La persona escribió: hacker eternal" in prompt
    assert prompt.rstrip().endswith("hacker eternal")


def test_el_esquema_estricto_pide_las_entidades() -> None:
    assert "entities" in TERMS_SCHEMA["required"]
    assert TERMS_SCHEMA["properties"]["entities"] == {
        "type": "array",
        "items": {"type": "string"},
    }


async def test_openai_devuelve_las_entidades() -> None:
    answer = VALID | {"place": None, "place_state": None, "entities": ["Eternal"]}
    llm = enricher(httpx2.Response(200, json=api_reply(json.dumps(answer), 400, 90)), seen=[])

    result = await llm.suggest_terms(REQUEST)

    assert result.entities == ("Eternal",)
    await llm.aclose()


async def test_gemini_devuelve_las_entidades_y_una_respuesta_vieja_trae_ninguna() -> None:
    models = FakeModels(
        reply(VALID | {"entities": ["Eternal", "LockBit"]}, 380, 80), reply(VALID, 380, 80)
    )
    llm = GeminiEnricher(models, "gemini-2.5-flash")

    with_entities = await llm.suggest_terms(REQUEST)
    without = await llm.suggest_terms(REQUEST)

    assert with_entities.entities == ("Eternal", "LockBit")
    assert without.entities == ()


def test_el_prompt_v3_dice_que_un_lugar_no_es_entidad() -> None:
    # Revisión del 18/11/2026 (hallazgo 3): pedía «nombres propios» sin decir
    # que un lugar no va ahí; con «Jalisco» en entities se tiraban las frases.
    prompt = build_terms_prompt(
        TermSuggestionRequest("robo de autos con violencia en Jalisco", 12, 6)
    )

    assert (
        "- Un lugar (país, estado, ciudad, alcaldía o colonia) NO va en entities: el lugar "
        'se busca aparte. Solo va si es parte de un nombre propio ("Cártel de Sinaloa", '
        '"Universidad de Guadalajara"), y entonces va el nombre completo.'
    ) in prompt
