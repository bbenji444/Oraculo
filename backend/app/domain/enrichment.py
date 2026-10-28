"""Lo que la IA aporta de cada nota y cuánto cuesta (especificación §10; ADR-0015).

La IA (Gemini detrás de ``LLMPort``) lee el texto de la nota y devuelve:

- **relevancia** para cada concepto de la búsqueda (con puntaje y razón);
- un **resumen** propio de 2–3 oraciones (nunca copia el artículo);
- el **tipo de evento** y su **fecha**, si están en el texto;
- las **menciones de lugar** (texto, no coordenadas), que resuelve el
  geolocalizador (§11).

Aquí están esos datos, el recorte del texto que se manda (para acotar el
costo) y el cálculo del costo en dólares.

No hace: no llama a la IA ni valida JSON (eso es el adaptador).
"""

from dataclasses import dataclass
from datetime import date

from app.domain.geocoding import Mention

# Caracteres del texto que se mandan a la IA: ~1,500 tokens en español. Una
# nota típica de la muestra real (16/10/2026) tenía de 1,670 a 5,894; el
# inicio de la nota trae lo esencial (quién, qué, dónde).
MAX_TEXT_CHARS = 6000
_TOKENS_PER_MILLION = 1_000_000
# Tokens que se suponen por nota para estimar el costo ANTES de gastar
# (ADR-0015: ~2,000 de entrada con el texto recortado y ~300 de salida). El
# costo real se registra con los tokens que reporta la IA.
ESTIMATED_TOKENS_IN_PER_ARTICLE = 2000
ESTIMATED_TOKENS_OUT_PER_ARTICLE = 300


@dataclass(frozen=True, slots=True)
class ConceptBrief:
    """Lo que la IA necesita saber de un concepto para juzgar relevancia.

    Attributes:
        concept_id: Id del concepto.
        name: Nombre ("Extorsión").
        description: Qué cubre.
        keywords: Palabras clave.
    """

    concept_id: int
    name: str
    description: str
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConceptJudgement:
    """Si la nota es relevante para un concepto.

    Attributes:
        concept_id: Id del concepto.
        is_relevant: Si lo es (en sentido literal: "secuestraron la agenda" no).
        relevance_score: De 0 a 1.
        relevance_reason: Por qué, en una oración.
    """

    concept_id: int
    is_relevant: bool
    relevance_score: float
    relevance_reason: str | None


@dataclass(frozen=True, slots=True)
class Enrichment:
    """Todo lo que la IA aportó de una nota.

    Attributes:
        concepts: Un juicio por concepto de la búsqueda.
        summary: Resumen propio, neutral, en español.
        event_type: Tipo de evento ("ransomware", "secuestro"...), si lo hay.
        event_date: Fecha de lo que informa la nota (la detención, la sentencia),
            si el texto la dice; desde ``enrich_v3``, no la del delito original.
        locations: Menciones de lugar para el geolocalizador.
    """

    concepts: tuple[ConceptJudgement, ...]
    summary: str | None
    event_type: str | None
    event_date: date | None
    locations: tuple[Mention, ...]


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Tokens que se gastaron en una llamada.

    Attributes:
        tokens_in: Tokens de entrada (prompt + texto).
        tokens_out: Tokens de salida (incluye "razonamiento", si lo hubo).
    """

    tokens_in: int
    tokens_out: int

    def cost_usd(self, price_in_per_million: float, price_out_per_million: float) -> float:
        """Costo de la llamada con los precios del modelo.

        Args:
            price_in_per_million: Dólares por millón de tokens de entrada.
            price_out_per_million: Dólares por millón de tokens de salida.

        Returns:
            Costo en dólares.

        Example:
            >>> LLMUsage(2000, 300).cost_usd(0.30, 2.50)
            0.00135
        """
        return (
            self.tokens_in * price_in_per_million + self.tokens_out * price_out_per_million
        ) / _TOKENS_PER_MILLION

    def __add__(self, other: "LLMUsage") -> "LLMUsage":
        """Suma los tokens de dos llamadas (total de una búsqueda)."""
        return LLMUsage(self.tokens_in + other.tokens_in, self.tokens_out + other.tokens_out)


def estimated_usage(articles: int) -> LLMUsage:
    """Tokens que se calculan para enriquecer cierta cantidad de notas, antes de gastar.

    Args:
        articles: Notas que se mandarían a la IA.

    Returns:
        Tokens estimados (ADR-0015).

    Example:
        >>> estimated_usage(150).cost_usd(0.10, 0.50)
        0.0525
    """
    return LLMUsage(
        articles * ESTIMATED_TOKENS_IN_PER_ARTICLE, articles * ESTIMATED_TOKENS_OUT_PER_ARTICLE
    )


def text_for_llm(text: str) -> str:
    """Recorta el texto que se manda a la IA para acotar el costo (ADR-0015).

    Args:
        text: Texto de la nota (cuerpo o título + fragmento).

    Returns:
        Hasta ``MAX_TEXT_CHARS`` caracteres, cortando en el último espacio.
    """
    if len(text) <= MAX_TEXT_CHARS:
        return text
    cut = text[:MAX_TEXT_CHARS]
    return cut[: cut.rfind(" ")] if " " in cut else cut
