"""Arma la IA según ``LLM_PROVIDER`` (ADR-0016).

Lo usan el pipeline de búsqueda y los comandos de prueba. Devuelve el
adaptador y los precios del modelo elegido, para estimar y registrar el
costo (ADR-0015).

No hace: no llama a ninguna IA.
"""

from dataclasses import dataclass

from app.adapters.llm.gemini import build_gemini
from app.adapters.llm.openai import build_openai
from app.application.ports.llm import LLMPort
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
    if settings.llm_provider == "openai":
        key = settings.openai_api_key
        if key is None or not key.get_secret_value():
            raise MissingLLMKeyError("Falta OPENAI_API_KEY en .env (LLM_PROVIDER=openai).")
        return LLMSetup(
            "openai",
            build_openai(
                key.get_secret_value(),
                settings.openai_model,
                settings.llm_timeout_seconds,
                settings.provider_max_attempts,
                settings.llm_concurrency,
            ),
            settings.openai_price_input_per_million,
            settings.openai_price_output_per_million,
        )
    key = settings.gemini_api_key
    if key is None or not key.get_secret_value():
        raise MissingLLMKeyError("Falta GEMINI_API_KEY en .env (LLM_PROVIDER=gemini).")
    return LLMSetup(
        "gemini",
        build_gemini(key.get_secret_value(), settings.gemini_model, settings.llm_timeout_seconds),
        settings.gemini_price_input_per_million,
        settings.gemini_price_output_per_million,
    )
