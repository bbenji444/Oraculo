"""Clasificación por categoría con la IA (F12.4, ADR-0029), con respuestas simuladas."""

import json
from typing import Any

import httpx2
import pytest

from app.adapters.llm.common import (
    CLASSIFY_PROMPT_VERSION,
    CLASSIFY_SUMMARY_CHARS,
    build_classify_prompt,
)
from app.adapters.llm.gemini import GeminiEnricher
from app.application.ports.llm import (
    CategoryOption,
    ClassificationError,
    ClassificationNote,
    ClassificationRequest,
)
from app.domain.enrichment import LLMUsage
from tests.unit.test_gemini import FakeModels, reply
from tests.unit.test_openai_llm import api_reply, enricher

pytestmark = pytest.mark.anyio

CATEGORIES = (
    CategoryOption("Armas y explosivos", "Tráfico o aseguramiento de armas."),
    CategoryOption("Corrupción", "Servidores públicos que abusan del cargo."),
    CategoryOption("Otros", "Lo que no encaje."),
)
REQUEST = ClassificationRequest(
    notes=(
        ClassificationNote(11, "FGR asegura armas en Sinaloa", "Aseguran 40 rifles en un cateo."),
        ClassificationNote(12, "Investigan a exfiscal por casinos", None),
    ),
    categories=CATEGORIES,
    other="Otros",
)


def test_el_prompt_lleva_el_catalogo_y_solo_titulo_y_resumen() -> None:
    long = ClassificationNote(13, "Nota larga", "x" * 2000)
    prompt = build_classify_prompt(
        ClassificationRequest((*REQUEST.notes, long), CATEGORIES, "Otros")
    )

    assert "- Armas y explosivos: Tráfico o aseguramiento de armas." in prompt
    assert "[11] FGR asegura armas en Sinaloa — Aseguran 40 rifles en un cateo." in prompt
    assert "[12] Investigan a exfiscal por casinos — sin resumen" in prompt
    assert "x" * (CLASSIFY_SUMMARY_CHARS + 1) not in prompt
    assert "usa «Otros»" in prompt


async def test_openai_clasifica_con_lista_cerrada_e_ignora_ids_ajenos() -> None:
    seen: list[dict[str, Any]] = []
    reply = {
        "items": [
            {"id": 11, "category": "Armas y explosivos", "label": "tráfico de armas"},
            {"id": 12, "category": "Corrupción", "label": "enriquecimiento ilícito"},
            # Id que no estaba en el lote y repetido: se ignoran.
            {"id": 99, "category": "Otros", "label": None},
            {"id": 11, "category": "Otros", "label": None},
        ]
    }
    llm = enricher(httpx2.Response(200, json=api_reply(json.dumps(reply), 900, 80)), seen=seen)

    result = await llm.classify(REQUEST)

    assert [(x.article_id, x.category, x.raw_label) for x in result.labels] == [
        (11, "Armas y explosivos", "tráfico de armas"),
        (12, "Corrupción", "enriquecimiento ilícito"),
    ]
    assert (result.usage, result.prompt_version) == (LLMUsage(900, 80), CLASSIFY_PROMPT_VERSION)
    schema = seen[0]["body"]["text"]["format"]["schema"]
    item = schema["properties"]["items"]["items"]
    assert item["properties"]["category"]["enum"] == [c.name for c in CATEGORIES]
    await llm.aclose()


async def test_respuesta_invalida_se_reintenta_y_luego_es_error() -> None:
    seen: list[dict[str, Any]] = []
    llm = enricher(
        httpx2.Response(200, json=api_reply('{"items": "no"}', 500, 10)),
        httpx2.Response(200, json=api_reply("nada", 500, 10)),
        seen=seen,
    )

    with pytest.raises(ClassificationError, match="OpenAI") as error:
        await llm.classify(REQUEST)

    assert error.value.usage == LLMUsage(1000, 20)
    await llm.aclose()


async def test_gemini_clasifica_con_el_mismo_prompt() -> None:
    models = FakeModels(
        reply({"items": [{"id": 12, "category": "Corrupción", "label": "casinos"}]})
    )
    llm = GeminiEnricher(models, "gemini-2.5-flash")

    result = await llm.classify(REQUEST)
    await llm.aclose()

    assert [(x.article_id, x.category, x.raw_label) for x in result.labels] == [
        (12, "Corrupción", "casinos")
    ]
    assert models.calls[0]["contents"] == build_classify_prompt(REQUEST)
