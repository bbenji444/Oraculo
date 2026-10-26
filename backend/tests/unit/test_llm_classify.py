"""Clasificación por categoría y quién actúa (F12.4–F12.5), con respuestas simuladas."""

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
from app.domain.authority import Authority
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
    # Quién actúa (F12.5): la fiscalía estatal y la simple mención no son la FGR.
    assert '"estatal": solo actúa una fiscalía o procuraduría de un estado' in prompt
    assert '"fgr_mencion": la FGR solo se nombra' in prompt


def test_el_prompt_lleva_lo_que_la_ia_anoto_al_leer_la_nota() -> None:
    # Nota 1401 del 24/10: el resumen no dice que participó la FGR; la razón sí.
    note = ClassificationNote(
        14, "EEUU imputa a capo de Jalisco", "Lo acusan en EEUU.", "Participaron agentes de la FGR."
    )
    prompt = build_classify_prompt(ClassificationRequest((note,), CATEGORIES, "Otros"))

    assert (
        "[14] EEUU imputa a capo de Jalisco — Lo acusan en EEUU. "
        "(Al leerla completa: Participaron agentes de la FGR.)"
    ) in prompt
    # Sin razones, la línea queda como antes.
    assert "[11] FGR asegura armas en Sinaloa — Aseguran 40 rifles en un cateo.\n" in (
        build_classify_prompt(REQUEST) + "\n"
    )


async def test_openai_clasifica_con_lista_cerrada_e_ignora_ids_ajenos() -> None:
    seen: list[dict[str, Any]] = []
    reply = {
        "items": [
            {
                "id": 11,
                "category": "Armas y explosivos",
                "label": "tráfico de armas",
                "authority": "fgr",
            },
            {
                "id": 12,
                "category": "Corrupción",
                "label": "enriquecimiento ilícito",
                "authority": "estatal",
            },
            # Id que no estaba en el lote y repetido: se ignoran.
            {"id": 99, "category": "Otros", "label": None, "authority": "otra"},
            {"id": 11, "category": "Otros", "label": None, "authority": "otra"},
        ]
    }
    llm = enricher(httpx2.Response(200, json=api_reply(json.dumps(reply), 900, 80)), seen=seen)

    result = await llm.classify(REQUEST)

    assert [(x.article_id, x.category, x.raw_label, x.authority) for x in result.labels] == [
        (11, "Armas y explosivos", "tráfico de armas", Authority.FGR),
        (12, "Corrupción", "enriquecimiento ilícito", Authority.STATE),
    ]
    assert (result.usage, result.prompt_version) == (LLMUsage(900, 80), CLASSIFY_PROMPT_VERSION)
    assert CLASSIFY_PROMPT_VERSION == "classify_v3"
    schema = seen[0]["body"]["text"]["format"]["schema"]
    item = schema["properties"]["items"]["items"]
    assert item["properties"]["category"]["enum"] == [c.name for c in CATEGORIES]
    assert item["properties"]["authority"]["enum"] == [
        "fgr",
        "fgr_mencion",
        "estatal",
        "otra",
        "sin_dato",
    ]
    assert "authority" in item["required"]
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
        reply(
            {
                "items": [
                    # Gemini no garantiza la lista cerrada: lo desconocido es sin_dato.
                    {"id": 11, "category": "Armas y explosivos", "authority": "policía"},
                    {"id": 12, "category": "Corrupción", "label": "casinos"},
                ]
            }
        )
    )
    llm = GeminiEnricher(models, "gemini-2.5-flash")

    result = await llm.classify(REQUEST)
    await llm.aclose()

    assert [(x.article_id, x.category, x.raw_label, x.authority) for x in result.labels] == [
        (11, "Armas y explosivos", None, Authority.UNKNOWN),
        (12, "Corrupción", "casinos", None),
    ]
    assert models.calls[0]["contents"] == build_classify_prompt(REQUEST)
