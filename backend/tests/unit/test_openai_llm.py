"""Adaptador de OpenAI y elección de IA, con respuestas simuladas: sin red ni gasto."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from app.adapters.llm.common import PROMPT_VERSION
from app.adapters.llm.factory import MissingLLMKeyError, build_llm, llm_info
from app.adapters.llm.gemini import GeminiEnricher
from app.adapters.llm.openai import (
    ENRICHMENT_SCHEMA,
    RESPONSES_URL,
    OpenAIEnricher,
    output_text,
    request_body,
)
from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.llm import EnrichmentError, EnrichmentRequest, LLMInfo
from app.core.config import Settings
from app.domain.enrichment import ConceptBrief, LLMUsage
from app.domain.errors import ProviderAuthError

EXTORSION = ConceptBrief(3, "Extorsión", "Cobro de piso", ("extorsión",))
REQUEST = EnrichmentRequest(
    "Detienen a dos por extorsión en Iztapalapa",
    "Detuvieron a dos personas en Iztapalapa por cobro de piso.",
    datetime(2026, 10, 16, tzinfo=UTC),
    [EXTORSION],
)
VALID = {
    "concepts": [
        {"concept_id": 3, "is_relevant": True, "relevance_score": 0.9, "relevance_reason": "Sí."}
    ],
    "summary": "Detienen a dos personas por extorsión.",
    "event_type": "extorsión",
    "event_date": "2026-10-16",
    "locations": [
        {
            "mention": "Iztapalapa",
            "kind_hint": "municipality",
            "state_hint": "Ciudad de México",
            "country": "México",
            "role": "event",
        }
    ],
}


def api_reply(text: str, tokens_in: int = 700, tokens_out: int = 120) -> dict[str, Any]:
    """Forma documentada de /v1/responses (ADR-0016)."""
    return {
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
    }


Handler = Callable[[httpx2.Request], httpx2.Response]


def enricher(*replies: httpx2.Response, seen: list[dict[str, Any]]) -> OpenAIEnricher:
    queue = list(replies)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(
            {
                "url": str(request.url),
                "body": json.loads(request.content),
                "auth": request.headers.get("authorization"),
            }
        )
        return queue.pop(0)

    http = ProviderHttpClient(
        "openai",
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=2,
        headers={"Authorization": "Bearer llave-de-prueba"},
        transport=httpx2.MockTransport(handler),
    )
    return OpenAIEnricher(http, "gpt-6-luna")


@pytest.mark.anyio
async def test_respuesta_valida_con_esquema_estricto_y_sin_razonamiento() -> None:
    seen: list[dict[str, Any]] = []
    llm = enricher(httpx2.Response(200, json=api_reply(json.dumps(VALID))), seen=seen)

    result = await llm.enrich(REQUEST)

    assert result.enrichment.summary == "Detienen a dos personas por extorsión."
    assert result.enrichment.locations[0].text == "Iztapalapa"
    assert (result.usage, result.model, result.prompt_version) == (
        LLMUsage(700, 120),
        "gpt-6-luna",
        PROMPT_VERSION,
    )
    [call] = seen
    assert call["url"] == RESPONSES_URL
    assert call["auth"] == "Bearer llave-de-prueba"
    body = call["body"]
    assert body["reasoning"] == {"effort": "none"}
    assert body["text"]["format"]["strict"] is True
    await llm.aclose()


@pytest.mark.anyio
async def test_json_invalido_se_reintenta_y_luego_es_error() -> None:
    seen: list[dict[str, Any]] = []
    bad = httpx2.Response(200, json=api_reply("{}", 500, 10))
    llm = enricher(bad, httpx2.Response(200, json=api_reply("no", 500, 10)), seen=seen)

    with pytest.raises(EnrichmentError, match="OpenAI") as error:
        await llm.enrich(REQUEST)

    assert error.value.usage == LLMUsage(1000, 20)
    assert "no cumplió el esquema" in seen[1]["body"]["input"][0]["content"]
    await llm.aclose()


@pytest.mark.anyio
async def test_llave_rechazada_es_error_de_autenticacion() -> None:
    llm = enricher(httpx2.Response(401, json={"error": {"message": "bad key"}}), seen=[])

    with pytest.raises(ProviderAuthError):
        await llm.enrich(REQUEST)
    await llm.aclose()


def test_rechazo_o_respuesta_cortada_no_trae_texto() -> None:
    refusal = {"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No."}]}]}

    assert output_text(refusal) == ""
    assert output_text({"status": "incomplete", "output": None}) == ""
    assert output_text({"output": ["raro", {"type": "message", "content": ["x"]}]}) == ""


def test_el_esquema_estricto_pide_todos_los_campos() -> None:
    def check(node: dict[str, Any]) -> None:
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                check(child)
        if node.get("type") == "array":
            check(node["items"])

    check(ENRICHMENT_SCHEMA)
    assert request_body("m", "p")["model"] == "m"


def settings(**values: Any) -> Settings:
    base: dict[str, Any] = {
        "llm_provider": "openai",
        "openai_api_key": None,
        "openai_model": "gpt-6-luna",
        "openai_price_input_per_million": 0.10,
        "openai_price_output_per_million": 0.50,
        "gemini_api_key": None,
        "gemini_model": "gemini-2.5-flash",
        "gemini_price_input_per_million": 0.30,
        "gemini_price_output_per_million": 2.50,
        "llm_timeout_seconds": 60,
        "provider_max_attempts": 3,
        "llm_concurrency": 4,
    }
    base.update(values)
    return Settings.model_construct(**base)


def test_la_fabrica_elige_el_proveedor_y_sus_precios() -> None:
    openai = build_llm(settings(openai_api_key=SecretStr("x")))
    gemini = build_llm(settings(llm_provider="gemini", gemini_api_key=SecretStr("y")))

    assert (openai.provider, openai.price_input_per_million) == ("openai", 0.10)
    assert isinstance(openai.llm, OpenAIEnricher)
    assert (gemini.provider, gemini.price_output_per_million) == ("gemini", 2.50)
    assert isinstance(gemini.llm, GeminiEnricher)


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_sin_llave_lo_dice_claro(provider: str) -> None:
    with pytest.raises(MissingLLMKeyError, match="API_KEY"):
        build_llm(settings(llm_provider=provider))


def test_la_tarifa_se_conoce_sin_llave() -> None:
    openai = llm_info(settings())
    gemini = llm_info(settings(llm_provider="gemini", gemini_api_key=SecretStr("y")))

    assert openai == LLMInfo("openai", "gpt-6-luna", 0.10, 0.50, configured=False)
    assert gemini == LLMInfo("gemini", "gemini-2.5-flash", 0.30, 2.50, configured=True)
