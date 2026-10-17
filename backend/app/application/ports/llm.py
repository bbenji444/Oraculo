"""Puerto de la IA que enriquece notas (``LLMPort``, especificación §10).

La implementación vigente es Gemini (``app/adapters/llm/gemini.py``); cambiar
de modelo o de proveedor es escribir otro adaptador.

No hace: no decide qué notas se enriquecen ni guarda nada.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.enrichment import ConceptBrief, Enrichment, LLMUsage


@dataclass(frozen=True, slots=True)
class EnrichmentRequest:
    """Lo que se le manda a la IA de una nota.

    Attributes:
        title: Título.
        text: Texto ya recortado (``text_for_llm``).
        published_at: Fecha de publicación, si se conoce (ayuda con
            "ayer", "el lunes").
        concepts: Conceptos de la búsqueda.
    """

    title: str
    text: str
    published_at: datetime | None
    concepts: Sequence[ConceptBrief]


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    """Respuesta de la IA con su costo y procedencia.

    Attributes:
        enrichment: Lo que aportó.
        usage: Tokens gastados (suma de intentos, si hubo reintento).
        model: Modelo usado.
        prompt_version: Versión del prompt (``enrich_v1``).
    """

    enrichment: Enrichment
    usage: LLMUsage
    model: str
    prompt_version: str


class EnrichmentError(RuntimeError):
    """La IA no dio una respuesta válida tras el reintento (va a ``processing_errors``).

    Attributes:
        usage: Tokens que sí se gastaron en los intentos fallidos.
    """

    def __init__(self, message: str, usage: LLMUsage) -> None:
        """Guarda el mensaje y lo gastado.

        Args:
            message: Qué falló, en español.
            usage: Tokens gastados aunque haya fallado.
        """
        super().__init__(message)
        self.usage = usage


class LLMPort(Protocol):
    """La IA que enriquece notas."""

    @property
    def model(self) -> str:
        """Modelo que se usa."""
        ...

    @property
    def prompt_version(self) -> str:
        """Versión del prompt (llave de la caché, §10)."""
        ...

    async def aclose(self) -> None:
        """Libera las conexiones al terminar la búsqueda."""
        ...

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        """Enriquece una nota.

        Args:
            request: Nota y conceptos.

        Returns:
            Relevancia, resumen, evento y lugares, con su costo.

        Raises:
            EnrichmentError: Si la respuesta no fue válida tras un reintento.
            ProviderError: Si la IA no respondió (red, 429, 5xx, llave).
        """
        ...
