"""Adaptador de Gemini con un modelo falso: sin red ni gasto (§10)."""

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from app.adapters.llm.common import PROMPT_VERSION, EnrichmentOut, build_prompt, to_enrichment
from app.adapters.llm.gemini import GeminiEnricher, build_gemini
from app.application.ports.llm import EnrichmentError, EnrichmentRequest
from app.domain.enrichment import MAX_TEXT_CHARS, ConceptBrief, LLMUsage, text_for_llm
from app.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.domain.geocoding import MentionRole
from app.domain.region import RegionLevel

pytestmark = pytest.mark.anyio

EXTORSION = ConceptBrief(3, "Extorsión", "Cobro de piso y amenazas", ("extorsión", "cobro de piso"))
REQUEST = EnrichmentRequest(
    title="Detienen a dos por extorsión en Iztapalapa",
    text="Elementos de seguridad detuvieron a dos personas en Iztapalapa por cobro de piso.",
    published_at=datetime(2026, 10, 16, 18, 0, tzinfo=UTC),
    concepts=[EXTORSION],
)
VALID = {
    "concepts": [
        {
            "concept_id": 3,
            "is_relevant": True,
            "relevance_score": 0.92,
            "relevance_reason": "Cobro de piso.",
        },
        {"concept_id": 99, "is_relevant": True, "relevance_score": 0.5},
    ],
    "summary": "Detienen a dos personas por extorsionar a comerciantes en Iztapalapa.",
    "event_type": "extorsión",
    "event_date": "2026-10-16",
    "locations": [
        {
            "mention": "Iztapalapa",
            "kind_hint": "municipality",
            "state_hint": "Ciudad de México",
            "country": "México",
            "role": "event",
        },
        {"mention": "Madrid", "country": "España", "role": "mentioned"},
    ],
}


def reply(body: object, tokens_in: int = 900, tokens_out: int = 150) -> SimpleNamespace:
    text = body if isinstance(body, str) else json.dumps(body)
    usage = SimpleNamespace(
        prompt_token_count=tokens_in, candidates_token_count=tokens_out, thoughts_token_count=None
    )
    return SimpleNamespace(text=text, usage_metadata=usage)


class FakeModels:
    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def generate_content(
        self, *, model: str, contents: str, config: types.GenerateContentConfig
    ) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def test_respuesta_valida_al_dominio() -> None:
    models = FakeModels(reply(VALID))

    llm = GeminiEnricher(models, "gemini-2.5-flash")
    result = await llm.enrich(REQUEST)
    await llm.aclose()

    enrichment = result.enrichment
    # El concepto que no se preguntó (99) se ignora.
    assert [c.concept_id for c in enrichment.concepts] == [3]
    assert enrichment.concepts[0].relevance_score == pytest.approx(0.92)
    assert enrichment.event_date == date(2026, 10, 16)
    iztapalapa, madrid = enrichment.locations
    assert (iztapalapa.text, iztapalapa.role, iztapalapa.kind_hint) == (
        "Iztapalapa",
        MentionRole.EVENT,
        RegionLevel.MUNICIPALITY,
    )
    assert madrid.is_abroad
    assert (result.usage, result.model, result.prompt_version) == (
        LLMUsage(900, 150),
        "gemini-2.5-flash",
        PROMPT_VERSION,
    )
    config = models.calls[0]["config"]
    # JSON con esquema y sin "razonamiento" cobrado.
    assert config.response_mime_type == "application/json"
    assert config.thinking_config.thinking_budget == 0


async def test_json_invalido_se_reintenta_una_vez_con_el_error() -> None:
    models = FakeModels(reply("no es json", 800, 20), reply(VALID, 900, 150))

    result = await GeminiEnricher(models, "m").enrich(REQUEST)

    assert len(models.calls) == 2
    assert "no cumplió el esquema" in models.calls[1]["contents"]
    assert result.usage == LLMUsage(1700, 170)


async def test_dos_respuestas_invalidas_son_error_con_lo_gastado() -> None:
    models = FakeModels(reply({"concepts": "x"}), reply({"summary": 3}))

    with pytest.raises(EnrichmentError, match="JSON válido") as error:
        await GeminiEnricher(models, "m").enrich(REQUEST)

    assert error.value.usage == LLMUsage(1800, 300)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (503, ProviderUnavailableError),
        (400, ProviderResponseError),
    ],
)
async def test_errores_de_gemini_se_traducen(code: int, expected: type[Exception]) -> None:
    failure = genai_errors.APIError(code, {"error": {"message": "fallo", "status": "X"}})

    with pytest.raises(expected):
        await GeminiEnricher(FakeModels(failure), "m").enrich(REQUEST)


def test_el_prompt_lleva_conceptos_fecha_y_texto() -> None:
    prompt = build_prompt(REQUEST)

    assert "concept_id 3: Extorsión" in prompt
    assert "2026-10-16" in prompt
    assert "cobro de piso" in prompt
    assert "No des coordenadas" in prompt


def test_sin_fecha_el_prompt_lo_dice() -> None:
    no_date = EnrichmentRequest("T", "x", None, [EXTORSION])

    assert "Fecha de publicación: desconocida" in build_prompt(no_date)


def test_el_texto_se_recorta_en_un_espacio() -> None:
    long = "palabra " * 2000

    cut = text_for_llm(long)

    assert len(cut) <= MAX_TEXT_CHARS
    assert not cut.endswith("palabr")
    assert text_for_llm("corto") == "corto"
    assert text_for_llm("x" * (MAX_TEXT_CHARS + 10)) == "x" * MAX_TEXT_CHARS


def test_costo_con_los_precios_de_gemini() -> None:
    assert LLMUsage(2000, 300).cost_usd(0.30, 2.50) == pytest.approx(0.00135)


def test_la_fabrica_crea_un_cliente_real_sin_llamar() -> None:
    enricher = build_gemini("llave-falsa", "gemini-2.5-flash", 60)

    assert (enricher.model, enricher.prompt_version) == ("gemini-2.5-flash", PROMPT_VERSION)


def test_prompt_v2_pide_el_municipio_de_colonias_y_calles() -> None:
    # Sin él, "Polanco" no se podía ubicar dentro de la CDMX (ADR-0020).
    prompt = build_prompt(REQUEST)

    assert PROMPT_VERSION == "enrich_v2"
    assert "municipality_hint" in prompt
    assert "Día de Muertos" in prompt


def test_el_municipio_que_sugiere_la_ia_llega_a_la_mencion() -> None:
    out = EnrichmentOut.model_validate(
        {
            "concepts": [],
            "locations": [
                {
                    "mention": "Polanco",
                    "kind_hint": "locality",
                    "state_hint": "Ciudad de México",
                    "municipality_hint": "Miguel Hidalgo",
                    "country": "México",
                    "role": "event",
                },
                # Respuestas grabadas con v1 no traen el campo: queda vacío.
                {"mention": "CDMX", "kind_hint": "state", "role": "mentioned"},
            ],
        }
    )

    polanco, cdmx = to_enrichment(out, set()).locations

    assert polanco.municipality_hint == "Miguel Hidalgo"
    assert cdmx.municipality_hint is None
