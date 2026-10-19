"""Resumen ejecutivo de los reportes con la IA simulada: sin red ni gasto (F7, ADR-0018)."""

import json
from datetime import UTC, date, datetime
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from app.adapters.llm.common import (
    MAX_SUMMARY_NOTES,
    SUMMARY_PROMPT_VERSION,
    build_summary_prompt,
)
from app.adapters.llm.factory import MissingLLMKeyError, build_summarizer
from app.adapters.llm.gemini import GeminiEnricher
from app.adapters.llm.openai import SUMMARY_SCHEMA, OpenAIEnricher
from app.application.ports.llm import SummaryError, SummaryNote, SummaryRequest
from app.domain.enrichment import LLMUsage
from tests.unit.test_gemini import FakeModels, reply
from tests.unit.test_openai_llm import api_reply, enricher, settings

pytestmark = pytest.mark.anyio

NOTES = [
    SummaryNote(
        title="Detienen a dos por cobro de piso en Peñón Blanco",
        summary="La policía detuvo a dos hombres por extorsionar a comerciantes.",
        place="Municipio Peñón Blanco",
        # 03:00 UTC del 17 es todavía el 16 en la Ciudad de México.
        published_at=datetime(2026, 10, 17, 3, 0, tzinfo=UTC),
    ),
    SummaryNote(
        title="Denuncian llamadas de extorsión",
        summary="Vecinos reportan llamadas que exigen pagos.",
        place=None,
        published_at=None,
    ),
]
REQUEST = SummaryRequest(
    concepts=["Extorsión"],
    region="Jalisco",
    date_from=date(2026, 10, 10),
    date_to=date(2026, 10, 17),
    notes=NOTES,
)
TEXT = "Predominan los casos de cobro de piso.\n\nSe concentran en Peñón Blanco."


def test_el_prompt_lleva_solo_resumenes_titulos_lugar_y_fecha() -> None:
    prompt = build_summary_prompt(REQUEST)

    assert "Conceptos buscados: Extorsión" in prompt
    assert "Región: Jalisco" in prompt
    assert "del 10/10/2026 al 17/10/2026" in prompt
    assert "Notas relevantes: 2" in prompt
    assert "[16/10/2026] Detienen a dos por cobro de piso en Peñón Blanco" in prompt
    assert "Municipio Peñón Blanco: La policía detuvo" in prompt
    assert "[sin fecha] Denuncian llamadas de extorsión — sin ubicación" in prompt


def test_el_prompt_tiene_un_tope_de_notas() -> None:
    many = SummaryRequest(
        ["Extorsión"],
        "Jalisco",
        date(2026, 10, 1),
        date(2026, 10, 17),
        [NOTES[1]] * (MAX_SUMMARY_NOTES + 5),
    )

    prompt = build_summary_prompt(many)

    assert f"Notas relevantes: {MAX_SUMMARY_NOTES + 5}" in prompt
    assert prompt.count("Denuncian llamadas") == MAX_SUMMARY_NOTES


async def test_openai_resume_con_su_esquema_estricto() -> None:
    seen: list[dict[str, Any]] = []
    body = json.dumps({"executive_summary": f"  {TEXT}  "})
    llm = enricher(httpx2.Response(200, json=api_reply(body, 1200, 180)), seen=seen)

    result = await llm.summarize(REQUEST)

    assert (result.text, result.usage) == (TEXT, LLMUsage(1200, 180))
    assert (result.model, result.prompt_version) == ("gpt-6-luna", SUMMARY_PROMPT_VERSION)
    assert llm.summary_prompt_version == SUMMARY_PROMPT_VERSION
    request = seen[0]["body"]
    assert request["text"]["format"]["name"] == "executive_summary"
    assert request["text"]["format"]["schema"] == SUMMARY_SCHEMA
    assert "Peñón Blanco" in request["input"][0]["content"]
    await llm.aclose()


async def test_openai_resumen_vacio_se_reintenta_y_luego_es_error() -> None:
    empty = json.dumps({"executive_summary": ""})
    llm = enricher(
        httpx2.Response(200, json=api_reply(empty, 800, 5)),
        httpx2.Response(200, json=api_reply("no", 800, 5)),
        seen=[],
    )

    with pytest.raises(SummaryError, match="OpenAI") as error:
        await llm.summarize(REQUEST)

    assert error.value.usage == LLMUsage(1600, 10)
    await llm.aclose()


async def test_gemini_resume_con_el_mismo_prompt() -> None:
    models = FakeModels(reply({"executive_summary": TEXT}, 1100, 170))
    llm = GeminiEnricher(models, "gemini-2.5-flash")

    result = await llm.summarize(REQUEST)

    assert (result.text, result.usage) == (TEXT, LLMUsage(1100, 170))
    assert result.prompt_version == SUMMARY_PROMPT_VERSION
    assert models.calls[0]["contents"] == build_summary_prompt(REQUEST)
    assert models.calls[0]["config"].thinking_config.thinking_budget == 0


async def test_gemini_respuesta_invalida_es_error_con_lo_gastado() -> None:
    llm = GeminiEnricher(FakeModels(reply("{}", 900, 3), reply("{}", 900, 3)), "gemini-2.5-flash")

    with pytest.raises(SummaryError, match="Gemini") as error:
        await llm.summarize(REQUEST)

    assert error.value.usage == LLMUsage(1800, 6)


def test_la_fabrica_del_resumen_usa_la_ia_elegida() -> None:
    openai = build_summarizer(settings(openai_api_key=SecretStr("x")))
    gemini = build_summarizer(settings(llm_provider="gemini", gemini_api_key=SecretStr("y")))

    assert (openai.provider, openai.price_output_per_million) == ("openai", 0.50)
    assert isinstance(openai.summarizer, OpenAIEnricher)
    assert (gemini.provider, gemini.price_input_per_million) == ("gemini", 0.30)
    assert isinstance(gemini.summarizer, GeminiEnricher)
    with pytest.raises(MissingLLMKeyError):
        build_summarizer(settings())
