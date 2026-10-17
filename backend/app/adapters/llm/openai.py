"""``LLMPort`` con OpenAI por HTTP (ADR-0016).

Confirmado en la documentación de OpenAI (17/10/2026):

- ``POST https://api.openai.com/v1/responses`` con ``Authorization: Bearer``;
- cuerpo: ``model``, ``input`` (mensajes), ``reasoning.effort`` y
  ``text.format = {type: "json_schema", name, schema, strict: true}``;
- respuesta: el JSON en ``output[].content[]`` con ``type = output_text``
  (o ``refusal`` si el modelo se niega); ``status`` e ``incomplete_details``
  avisan si se cortó;
- uso: ``usage.input_tokens`` y ``usage.output_tokens`` (incluye el
  razonamiento, si lo hubo).

Sin SDK: una sola petición con el cliente HTTP compartido, que ya pone
tiempo máximo, reintentos ante 429 y 5xx, y traduce los errores (ADR-0010).
El razonamiento se apaga (``effort: none``): se cobra y no hace falta.

El modo estricto de OpenAI exige que todos los campos estén en ``required``
y ``additionalProperties: false``; por eso el esquema está escrito a mano.
La respuesta se valida con el mismo ``EnrichmentOut`` que Gemini.

No hace: no decide qué notas se enriquecen ni guarda nada.
"""

import json
from typing import Any

from pydantic import ValidationError

from app.adapters.llm.common import (
    MAX_OUTPUT_TOKENS,
    PROMPT_VERSION,
    RETRY_ERROR_CHARS,
    RETRY_NOTE,
    EnrichmentOut,
    build_prompt,
    to_enrichment,
)
from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.llm import EnrichmentError, EnrichmentRequest, EnrichmentResult
from app.domain.enrichment import LLMUsage

RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI = "openai"
# Sin razonamiento: para extraer datos de una nota no hace falta y se cobra.
REASONING_EFFORT = "none"
_NULLABLE_TEXT = {"type": ["string", "null"]}

# Esquema estricto de la respuesta (mismo contenido que EnrichmentOut).
ENRICHMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["concepts", "summary", "event_type", "event_date", "locations"],
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["concept_id", "is_relevant", "relevance_score", "relevance_reason"],
                "properties": {
                    "concept_id": {"type": "integer"},
                    "is_relevant": {"type": "boolean"},
                    "relevance_score": {"type": "number"},
                    "relevance_reason": _NULLABLE_TEXT,
                },
            },
        },
        "summary": _NULLABLE_TEXT,
        "event_type": _NULLABLE_TEXT,
        "event_date": {"type": ["string", "null"], "description": "AAAA-MM-DD"},
        "locations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["mention", "kind_hint", "state_hint", "country", "role"],
                "properties": {
                    "mention": {"type": "string"},
                    "kind_hint": {
                        "type": ["string", "null"],
                        "enum": ["country", "state", "municipality", "locality", None],
                    },
                    "state_hint": _NULLABLE_TEXT,
                    "country": _NULLABLE_TEXT,
                    "role": {"type": "string", "enum": ["event", "mentioned"]},
                },
            },
        },
    },
}


def request_body(model: str, prompt: str) -> dict[str, Any]:
    """Cuerpo de la petición a ``/v1/responses``.

    Args:
        model: Modelo (``OPENAI_MODEL``).
        prompt: Prompt ya lleno.

    Returns:
        El cuerpo JSON.
    """
    return {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
        "reasoning": {"effort": REASONING_EFFORT},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "enrichment",
                "schema": ENRICHMENT_SCHEMA,
                "strict": True,
            }
        },
    }


def output_text(data: dict[str, Any]) -> str:
    """Saca el texto JSON de la respuesta.

    Args:
        data: Respuesta de ``/v1/responses``.

    Returns:
        El texto de la primera parte ``output_text``, o ``""`` si no hay
        (respuesta cortada o rechazo): la validación lo marcará inválido.
    """
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                return str(part.get("text") or "")
    return ""


def usage_of(data: dict[str, Any]) -> LLMUsage:
    """Tokens que reporta la respuesta.

    Args:
        data: Respuesta de ``/v1/responses``.

    Returns:
        Tokens de entrada y salida (0 si no vienen).
    """
    usage = data.get("usage") or {}
    return LLMUsage(int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0))


class OpenAIEnricher:
    """``LLMPort`` sobre la API de respuestas de OpenAI."""

    def __init__(self, http: ProviderHttpClient, model: str) -> None:
        """Recibe el cliente HTTP (con la llave en el encabezado) y el modelo.

        Args:
            http: Cliente HTTP compartido configurado para OpenAI.
            model: ``OPENAI_MODEL``.
        """
        self._http = http
        self._model = model

    @property
    def model(self) -> str:
        """Ver ``LLMPort.model``."""
        return self._model

    @property
    def prompt_version(self) -> str:
        """Ver ``LLMPort.prompt_version``."""
        return PROMPT_VERSION

    async def aclose(self) -> None:
        """Cierra las conexiones HTTP."""
        await self._http.aclose()

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        """Ver ``LLMPort.enrich``."""
        prompt = build_prompt(request)
        concept_ids = {c.concept_id for c in request.concepts}
        tokens_in = tokens_out = 0
        contents = prompt
        last_error = ""
        for _attempt in range(2):
            response = await self._http.post_json(
                RESPONSES_URL, request_body(self._model, contents)
            )
            data = json.loads(response.text or "{}")
            usage = usage_of(data)
            tokens_in += usage.tokens_in
            tokens_out += usage.tokens_out
            try:
                out = EnrichmentOut.model_validate_json(output_text(data))
            except ValidationError as error:
                last_error = str(error)[:RETRY_ERROR_CHARS]
                contents = prompt + RETRY_NOTE.format(error=last_error)
                continue
            return EnrichmentResult(
                to_enrichment(out, concept_ids),
                LLMUsage(tokens_in, tokens_out),
                self._model,
                PROMPT_VERSION,
            )
        raise EnrichmentError(
            f"OpenAI no dio un JSON válido tras reintentar: {last_error}",
            LLMUsage(tokens_in, tokens_out),
        )


def build_openai(
    api_key: str, model: str, timeout_seconds: float, max_attempts: int, concurrency: int
) -> OpenAIEnricher:
    """Crea el adaptador con la llave en el encabezado.

    Args:
        api_key: ``OPENAI_API_KEY`` (va en ``Authorization``; nunca se registra).
        model: ``OPENAI_MODEL``.
        timeout_seconds: Tiempo máximo por llamada.
        max_attempts: Intentos ante 429, 5xx o red caída.
        concurrency: Llamadas simultáneas (LLM_CONCURRENCY).

    Returns:
        El adaptador.
    """
    http = ProviderHttpClient(
        OPENAI,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        max_concurrency=concurrency,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return OpenAIEnricher(http, model)
