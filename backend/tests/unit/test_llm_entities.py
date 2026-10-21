"""Entidades de una nota con la IA simulada: sin red ni gasto (Fase 9.4, ADR-0103).

La nota es inventada (nombres ficticios) y las respuestas tienen la forma
documentada de cada proveedor (``/v1/responses`` de OpenAI y el SDK de
Gemini), igual que las demás pruebas de la IA.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from app.adapters.llm.common import (
    ENTITIES_PROMPT_VERSION,
    EntitiesOut,
    build_entities_prompt,
    to_raw_proposals,
)
from app.adapters.llm.factory import MissingLLMKeyError, build_entity_extractor
from app.adapters.llm.gemini import GeminiEnricher
from app.adapters.llm.openai import ENTITIES_SCHEMA, OpenAIEnricher
from app.application.ports.llm import EntityExtractionError, EntityExtractionRequest
from app.domain.enrichment import LLMUsage
from app.domain.investigation import LegalStatus
from tests.unit.test_gemini import FakeModels, reply
from tests.unit.test_openai_llm import api_reply, enricher, settings

pytestmark = pytest.mark.anyio

REQUEST = EntityExtractionRequest(
    title="Giran orden de aprehensión contra empresario por homicidio en Polanco",
    text=(
        "Un juez emitió una orden de aprehensión contra el empresario Julián Ortega Ruiz, "
        "señalado por el asesinato del estilista Ramón Salas en la colonia Polanco."
    ),
    published_at=datetime(2026, 10, 9, 18, tzinfo=UTC),
)
VALID = {
    "entities": [
        {
            "type": "person",
            "label": "Julián Ortega Ruiz",
            "aliases": ["Julián N"],
            "role": "event",
            "legal_status_hint": "alleged",
            "confidence": 0.9,
            "evidence_span": "una orden de aprehensión contra el empresario Julián Ortega Ruiz",
        },
        {
            "type": "place",
            "label": "Polanco",
            "aliases": [],
            "role": "event",
            "legal_status_hint": None,
            "confidence": 0.8,
            "evidence_span": "en la colonia Polanco",
        },
    ]
}


def test_el_prompt_lleva_la_nota_y_las_reglas_estrictas() -> None:
    prompt = build_entities_prompt(REQUEST)

    assert "Fecha de publicación: 2026-10-09" in prompt
    assert f"Título: {REQUEST.title}" in prompt
    assert REQUEST.text in prompt
    assert "Solo lo que dice el texto" in prompt
    assert 'No existe "culpable"' in prompt
    assert "evidence_span: una cita LITERAL" in prompt
    for status in LegalStatus:
        assert f'"{status.value}"' in prompt


def test_sin_fecha_el_prompt_lo_dice() -> None:
    undated = EntityExtractionRequest("Título", "Texto", None)

    assert "Fecha de publicación: desconocida" in build_entities_prompt(undated)


def test_la_respuesta_valida_se_vuelve_propuestas_sin_revisar() -> None:
    proposals = to_raw_proposals(EntitiesOut.model_validate(VALID))

    person, place = proposals
    assert (person.type, person.label, person.aliases) == (
        "person",
        "Julián Ortega Ruiz",
        ("Julián N",),
    )
    assert (person.legal_status_hint, person.confidence) == ("alleged", 0.9)
    assert (place.type, place.legal_status_hint) == ("place", None)


def test_el_esquema_estricto_de_openai_no_admite_culpable_ni_otros_tipos() -> None:
    item = ENTITIES_SCHEMA["properties"]["entities"]["items"]

    assert set(item["required"]) == set(item["properties"])
    assert item["additionalProperties"] is False
    assert item["properties"]["type"]["enum"] == ["org", "person", "place", "vehicle"]
    statuses = item["properties"]["legal_status_hint"]["enum"]
    assert "culpable" not in statuses
    assert set(statuses) == {*(s.value for s in LegalStatus), None}


async def test_openai_extrae_con_su_esquema_estricto() -> None:
    seen: list[dict[str, Any]] = []
    llm = enricher(httpx2.Response(200, json=api_reply(json.dumps(VALID), 1500, 400)), seen=seen)

    result = await llm.extract_entities(REQUEST)

    assert result.usage == LLMUsage(1500, 400)
    assert (result.model, result.prompt_version) == ("gpt-6-luna", ENTITIES_PROMPT_VERSION)
    assert llm.entities_prompt_version == ENTITIES_PROMPT_VERSION
    assert [p.label for p in result.proposals] == ["Julián Ortega Ruiz", "Polanco"]
    request = seen[0]["body"]
    assert request["text"]["format"] == {
        "type": "json_schema",
        "name": "entities",
        "schema": ENTITIES_SCHEMA,
        "strict": True,
    }
    assert request["input"][0]["content"] == build_entities_prompt(REQUEST)
    await llm.aclose()


async def test_openai_reintenta_una_vez_con_el_error() -> None:
    seen: list[dict[str, Any]] = []
    llm = enricher(
        httpx2.Response(200, json=api_reply('{"entidades": []}', 1500, 10)),
        httpx2.Response(200, json=api_reply(json.dumps(VALID), 1600, 400)),
        seen=seen,
    )

    result = await llm.extract_entities(REQUEST)

    assert len(result.proposals) == 2
    # Se cobra lo de los dos intentos.
    assert result.usage == LLMUsage(3100, 410)
    assert "no cumplió el esquema" in seen[1]["body"]["input"][0]["content"]
    await llm.aclose()


async def test_openai_dos_respuestas_invalidas_son_error_con_lo_gastado() -> None:
    llm = enricher(
        httpx2.Response(200, json=api_reply("no es json", 1500, 5)),
        httpx2.Response(200, json=api_reply("{}", 1500, 5)),
        seen=[],
    )

    with pytest.raises(EntityExtractionError, match="OpenAI") as error:
        await llm.extract_entities(REQUEST)

    assert error.value.usage == LLMUsage(3000, 10)
    await llm.aclose()


async def test_gemini_extrae_con_el_mismo_prompt_y_esquema() -> None:
    models = FakeModels(reply(VALID, 1400, 380))
    llm = GeminiEnricher(models, "gemini-2.5-flash")

    result = await llm.extract_entities(REQUEST)

    assert result.usage == LLMUsage(1400, 380)
    assert result.prompt_version == ENTITIES_PROMPT_VERSION
    assert llm.entities_prompt_version == ENTITIES_PROMPT_VERSION
    assert result.proposals[0].legal_status_hint == "alleged"
    call = models.calls[0]
    assert call["contents"] == build_entities_prompt(REQUEST)
    assert call["config"].response_schema is EntitiesOut
    assert call["config"].thinking_config.thinking_budget == 0


async def test_gemini_respuesta_invalida_es_error_con_lo_gastado() -> None:
    llm = GeminiEnricher(FakeModels(reply("[]", 900, 3), reply("{}", 900, 3)), "gemini-2.5-flash")

    with pytest.raises(EntityExtractionError, match="Gemini") as error:
        await llm.extract_entities(REQUEST)

    assert error.value.usage == LLMUsage(1800, 6)


def test_la_fabrica_de_entidades_usa_la_ia_elegida_y_sus_precios() -> None:
    openai = build_entity_extractor(settings(openai_api_key=SecretStr("x")))
    gemini = build_entity_extractor(settings(llm_provider="gemini", gemini_api_key=SecretStr("y")))

    assert (openai.provider, openai.price_input_per_million) == ("openai", 0.10)
    assert isinstance(openai.extractor, OpenAIEnricher)
    assert (gemini.provider, gemini.price_output_per_million) == ("gemini", 2.50)
    assert isinstance(gemini.extractor, GeminiEnricher)
    with pytest.raises(MissingLLMKeyError):
        build_entity_extractor(settings())
