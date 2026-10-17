"""``LLMPort`` con Gemini (especificación §10; ADR-0015).

Usa el SDK oficial ``google-genai`` 1.20 (la 2.x choca con tenacity 9.2.1,
ADR-0010). Firmas confirmadas con la versión instalada:

- ``Client(api_key=..., http_options=HttpOptions(timeout=...))``;
- ``client.aio.models.generate_content(model=..., contents=..., config=...)``;
- ``GenerateContentConfig(system_instruction, temperature, response_mime_type,
  response_schema, thinking_config, max_output_tokens)``;
- ``usage_metadata.prompt_token_count``, ``candidates_token_count`` y
  ``thoughts_token_count``;
- errores ``google.genai.errors.APIError`` con ``code`` (HTTP).

La respuesta se pide como JSON con el esquema de ``EnrichmentOut`` y se
valida con Pydantic. Si no valida, se reintenta **una vez** con el error
incluido; si vuelve a fallar, ``EnrichmentError`` (§10).

El "razonamiento" de Gemini 2.5 Flash se apaga (``thinking_budget=0``): se
cobra como salida y para extraer datos de una nota no hace falta.

No hace: no decide qué notas se enriquecen ni guarda nada.
"""

from typing import Any, Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from app.adapters.llm.common import (
    MAX_OUTPUT_TOKENS,
    PROMPT_VERSION,
    RETRY_ERROR_CHARS,
    RETRY_NOTE,
    TEMPERATURE,
    EnrichmentOut,
    build_prompt,
    to_enrichment,
)
from app.application.ports.llm import EnrichmentError, EnrichmentRequest, EnrichmentResult
from app.domain.enrichment import LLMUsage
from app.domain.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)

GEMINI = "gemini"
_MS_PER_SECOND = 1000
_AUTH_CODES = frozenset({401, 403})
_TOO_MANY = 429
_SERVER_ERROR = 500


class _Models(Protocol):
    async def generate_content(
        self, *, model: str, contents: str, config: types.GenerateContentConfig
    ) -> Any: ...


def _usage(response: Any) -> LLMUsage:
    meta = getattr(response, "usage_metadata", None)
    tokens_in = getattr(meta, "prompt_token_count", None) or 0
    tokens_out = (getattr(meta, "candidates_token_count", None) or 0) + (
        getattr(meta, "thoughts_token_count", None) or 0
    )
    return LLMUsage(int(tokens_in), int(tokens_out))


def _translate(error: genai_errors.APIError) -> ProviderError:
    code = error.code
    if code in _AUTH_CODES:
        return ProviderAuthError(
            f"Gemini rechazó la llave (HTTP {code}). Revisa GEMINI_API_KEY.",
            provider=GEMINI,
            http_status=code,
        )
    if code == _TOO_MANY:
        return ProviderRateLimitError(
            "Gemini pidió ir más despacio (HTTP 429).", provider=GEMINI, http_status=code
        )
    if code >= _SERVER_ERROR:
        return ProviderUnavailableError(
            f"Gemini tuvo un error del servidor (HTTP {code}).", provider=GEMINI, http_status=code
        )
    return ProviderResponseError(
        f"Gemini rechazó la petición (HTTP {code}): {str(error)[:300]}",
        provider=GEMINI,
        http_status=code,
    )


class GeminiEnricher:
    """``LLMPort`` sobre Gemini."""

    def __init__(self, models: _Models, model: str) -> None:
        """Recibe el cliente de modelos (las pruebas pasan uno falso) y el modelo.

        Args:
            models: ``client.aio.models`` del SDK.
            model: Nombre del modelo (``LLM_MODEL``).
        """
        self._models = models
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
        """Ver ``LLMPort.aclose``.

        VERIFICAR: la documentación de google-genai 1.20 no muestra un cierre
        explícito del cliente asíncrono; el SDK administra sus conexiones.
        """

    def _config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=EnrichmentOut,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

    async def _call(self, contents: str) -> Any:
        try:
            return await self._models.generate_content(
                model=self._model, contents=contents, config=self._config()
            )
        except genai_errors.APIError as error:
            raise _translate(error) from error

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        """Ver ``LLMPort.enrich``."""
        prompt = build_prompt(request)
        concept_ids = {c.concept_id for c in request.concepts}
        tokens_in = tokens_out = 0
        contents = prompt
        last_error = ""
        for _attempt in range(2):
            response = await self._call(contents)
            usage = _usage(response)
            tokens_in += usage.tokens_in
            tokens_out += usage.tokens_out
            try:
                out = EnrichmentOut.model_validate_json(getattr(response, "text", None) or "")
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
            f"Gemini no dio un JSON válido tras reintentar: {last_error}",
            LLMUsage(tokens_in, tokens_out),
        )


def build_gemini(api_key: str, model: str, timeout_seconds: float) -> GeminiEnricher:
    """Crea el adaptador con un cliente real del SDK.

    Args:
        api_key: ``GEMINI_API_KEY`` (nunca se registra).
        model: ``LLM_MODEL``.
        timeout_seconds: Tiempo máximo por llamada.

    Returns:
        El adaptador.
    """
    # VERIFICAR: la documentación del SDK indica el timeout de HttpOptions en
    # milisegundos; se confirma con la primera llamada real.
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=int(timeout_seconds * _MS_PER_SECOND)),
    )
    return GeminiEnricher(client.aio.models, model)
