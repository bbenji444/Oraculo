"""Arma la IA según ``LLM_PROVIDER`` (ADR-0016).

Lo usan el pipeline de búsqueda, la API y los comandos. ``llm_info`` dice
qué modelo se usaría y cuánto cobra sin crear el cliente (la estimación de
costo no necesita la llave); ``build_llm`` crea el adaptador.

No hace: no llama a ninguna IA.
"""

from dataclasses import dataclass

from app.adapters.llm.gemini import build_gemini
from app.adapters.llm.openai import build_openai
from app.application.ports.llm import LLMInfo, LLMPort
from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class LLMSetup:
    """La IA elegida y lo que cuesta.

    Attributes:
        provider: ``openai`` o ``gemini``.
        llm: El adaptador.
        price_input_per_million: Dólares por millón de tokens de entrada.
        price_output_per_million: Dólares por millón de tokens de salida.
    """

    provider: str
    llm: LLMPort
    price_input_per_million: float
    price_output_per_million: float


class MissingLLMKeyError(RuntimeError):
    """Falta la llave del proveedor de IA elegido en ``.env``."""


def _key(settings: Settings) -> str | None:
    secret = (
        settings.openai_api_key if settings.llm_provider == "openai" else (settings.gemini_api_key)
    )
    value = secret.get_secret_value() if secret is not None else ""
    return value or None


def llm_info(settings: Settings) -> LLMInfo:
    """Qué IA se usaría y sus precios, sin crear el cliente.

    Args:
        settings: Configuración (``LLM_PROVIDER`` y el modelo y precios de
            ese proveedor).

    Returns:
        Proveedor, modelo, precios y si su llave está configurada.
    """
    configured = _key(settings) is not None
    if settings.llm_provider == "openai":
        return LLMInfo(
            "openai",
            settings.openai_model,
            settings.openai_price_input_per_million,
            settings.openai_price_output_per_million,
            configured,
        )
    return LLMInfo(
        "gemini",
        settings.gemini_model,
        settings.gemini_price_input_per_million,
        settings.gemini_price_output_per_million,
        configured,
    )


def build_llm(settings: Settings) -> LLMSetup:
    """Crea la IA del proveedor elegido.

    Args:
        settings: Configuración (``LLM_PROVIDER`` y la llave y modelo de ese
            proveedor).

    Returns:
        El adaptador con sus precios.

    Raises:
        MissingLLMKeyError: Si falta la llave del proveedor elegido.
    """
    info = llm_info(settings)
    key = _key(settings)
    if key is None:
        name = "OPENAI_API_KEY" if info.provider == "openai" else "GEMINI_API_KEY"
        raise MissingLLMKeyError(f"Falta {name} en .env (LLM_PROVIDER={info.provider}).")
    llm: LLMPort
    if info.provider == "openai":
        llm = build_openai(
            key,
            info.model,
            settings.llm_timeout_seconds,
            settings.provider_max_attempts,
            settings.llm_concurrency,
        )
    else:
        llm = build_gemini(key, info.model, settings.llm_timeout_seconds)
    return LLMSetup(info.provider, llm, info.price_input_per_million, info.price_output_per_million)
