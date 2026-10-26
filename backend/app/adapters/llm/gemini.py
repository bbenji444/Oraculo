"""``LLMPort``, ``SummarizerPort`` y ``EntityExtractorPort`` con Gemini (§10, §15 y Fase 9.4).

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
from pydantic import BaseModel, ValidationError

from app.adapters.llm.common import (
    CLASSIFY_MAX_OUTPUT_TOKENS,
    CLASSIFY_PROMPT_VERSION,
    ENTITIES_MAX_OUTPUT_TOKENS,
    ENTITIES_PROMPT_VERSION,
    MAX_OUTPUT_TOKENS,
    PROMPT_VERSION,
    RETRY_ERROR_CHARS,
    RETRY_NOTE,
    SUMMARY_MAX_OUTPUT_TOKENS,
    SUMMARY_PROMPT_VERSION,
    TEMPERATURE,
    ClassificationOut,
    EnrichmentOut,
    EntitiesOut,
    SummaryOut,
    build_classify_prompt,
    build_entities_prompt,
    build_prompt,
    build_summary_prompt,
    to_enrichment,
    to_labels,
    to_raw_proposals,
)
from app.application.ports.llm import (
    ClassificationError,
    ClassificationRequest,
    ClassificationResult,
    EnrichmentError,
    EnrichmentRequest,
    EnrichmentResult,
    EntityExtractionError,
    EntityExtractionRequest,
    EntityExtractionResult,
    SummaryError,
    SummaryRequest,
    SummaryResult,
)
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

    @property
    def summary_prompt_version(self) -> str:
        """Ver ``SummarizerPort.summary_prompt_version``."""
        return SUMMARY_PROMPT_VERSION

    @property
    def classify_prompt_version(self) -> str:
        """Ver ``ClassifierPort.classify_prompt_version``."""
        return CLASSIFY_PROMPT_VERSION

    @property
    def entities_prompt_version(self) -> str:
        """Ver ``EntityExtractorPort.entities_prompt_version``."""
        return ENTITIES_PROMPT_VERSION

    async def aclose(self) -> None:
        """Ver ``LLMPort.aclose``.

        VERIFICAR: la documentación de google-genai 1.20 no muestra un cierre
        explícito del cliente asíncrono; el SDK administra sus conexiones.
        """

    def _config(
        self, schema: type[BaseModel], max_output_tokens: int
    ) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=TEMPERATURE,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

    async def _call(self, contents: str, config: types.GenerateContentConfig) -> Any:
        try:
            return await self._models.generate_content(
                model=self._model, contents=contents, config=config
            )
        except genai_errors.APIError as error:
            raise _translate(error) from error

    async def _complete[T: BaseModel](
        self, prompt: str, out_model: type[T], max_output_tokens: int
    ) -> tuple[T | None, LLMUsage, str]:
        """Pide un JSON, lo valida y reintenta una vez con el error (§10).

        Args:
            prompt: Prompt ya lleno.
            out_model: Modelo de Pydantic que valida la respuesta (también
                es el esquema que se le pide a Gemini).
            max_output_tokens: Tope de la respuesta.

        Returns:
            La respuesta validada (o ``None`` si no validó en los dos
            intentos), los tokens de los dos intentos y el último error.
        """
        config = self._config(out_model, max_output_tokens)
        tokens_in = tokens_out = 0
        contents = prompt
        last_error = ""
        for _attempt in range(2):
            response = await self._call(contents, config)
            usage = _usage(response)
            tokens_in += usage.tokens_in
            tokens_out += usage.tokens_out
            try:
                out = out_model.model_validate_json(getattr(response, "text", None) or "")
            except ValidationError as error:
                last_error = str(error)[:RETRY_ERROR_CHARS]
                contents = prompt + RETRY_NOTE.format(error=last_error)
                continue
            return out, LLMUsage(tokens_in, tokens_out), ""
        return None, LLMUsage(tokens_in, tokens_out), last_error

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        """Ver ``LLMPort.enrich``."""
        out, usage, error = await self._complete(
            build_prompt(request), EnrichmentOut, MAX_OUTPUT_TOKENS
        )
        if out is None:
            raise EnrichmentError(f"Gemini no dio un JSON válido tras reintentar: {error}", usage)
        concept_ids = {c.concept_id for c in request.concepts}
        return EnrichmentResult(to_enrichment(out, concept_ids), usage, self._model, PROMPT_VERSION)

    async def summarize(self, request: SummaryRequest) -> SummaryResult:
        """Ver ``SummarizerPort.summarize``."""
        out, usage, error = await self._complete(
            build_summary_prompt(request), SummaryOut, SUMMARY_MAX_OUTPUT_TOKENS
        )
        if out is None:
            raise SummaryError(f"Gemini no dio un resumen válido tras reintentar: {error}", usage)
        return SummaryResult(out.executive_summary, usage, self._model, SUMMARY_PROMPT_VERSION)

    async def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """Ver ``ClassifierPort.classify``."""
        out, usage, error = await self._complete(
            build_classify_prompt(request), ClassificationOut, CLASSIFY_MAX_OUTPUT_TOKENS
        )
        if out is None:
            raise ClassificationError(
                f"Gemini no dio una clasificación válida tras reintentar: {error}", usage
            )
        return ClassificationResult(
            to_labels(out, request), usage, self._model, CLASSIFY_PROMPT_VERSION
        )

    async def extract_entities(self, request: EntityExtractionRequest) -> EntityExtractionResult:
        """Ver ``EntityExtractorPort.extract_entities``."""
        out, usage, error = await self._complete(
            build_entities_prompt(request), EntitiesOut, ENTITIES_MAX_OUTPUT_TOKENS
        )
        if out is None:
            raise EntityExtractionError(
                f"Gemini no dio un JSON de entidades válido tras reintentar: {error}", usage
            )
        return EntityExtractionResult(
            to_raw_proposals(out), usage, self._model, ENTITIES_PROMPT_VERSION
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
