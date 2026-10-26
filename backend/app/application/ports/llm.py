"""Puertos de la IA: enriquecer notas, resumir reportes y proponer entidades.

``LLMPort`` enriquece (§10), ``SummarizerPort`` resume (§15) y
``EntityExtractorPort`` propone las entidades de una nota de un caso (Fase
9.4). Los implementan los adaptadores de OpenAI y Gemini (``app/adapters/llm/``),
elegidos con ``LLM_PROVIDER`` (ADR-0016). Son tres puertos porque los usan
casos de uso distintos: el pipeline de búsqueda solo enriquece, el reporte
solo resume y los casos de investigación solo extraen entidades.

No hace: no decide qué notas se enriquecen ni guarda nada.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from app.domain.authority import Authority
from app.domain.enrichment import ConceptBrief, Enrichment, LLMUsage
from app.domain.entity_extraction import RawProposal


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
        prompt_version: Versión del prompt (``enrich_v2``).
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


@dataclass(frozen=True, slots=True)
class LLMInfo:
    """Qué IA se usaría y cuánto cobra, sin crear el cliente (para estimar).

    Attributes:
        provider: ``openai`` o ``gemini`` (``LLM_PROVIDER``).
        model: Modelo configurado.
        price_input_per_million: Dólares por millón de tokens de entrada.
        price_output_per_million: Dólares por millón de tokens de salida.
        configured: Si su llave está en ``.env`` (sin ella no se puede buscar).
    """

    provider: str
    model: str
    price_input_per_million: float
    price_output_per_million: float
    configured: bool


@dataclass(frozen=True, slots=True)
class SummaryNote:
    """Una nota relevante tal como se le da a la IA para el resumen ejecutivo.

    Solo metadatos y el resumen ya generado: nunca el texto de la nota (§8).

    Attributes:
        title: Título.
        summary: Resumen generado al enriquecerla.
        place: Lugar principal ya ubicado ("Municipio Zapopan"), o ``None``.
        published_at: Fecha de publicación, si se conoce.
    """

    title: str
    summary: str
    place: str | None
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class SummaryRequest:
    """Lo que se le pide a la IA para el resumen ejecutivo de un reporte.

    Attributes:
        concepts: Nombres de los conceptos buscados.
        region: Región de la búsqueda ("México › Jalisco").
        date_from: Primer día del rango.
        date_to: Último día del rango.
        notes: Notas relevantes, de la más reciente a la más vieja.
    """

    concepts: Sequence[str]
    region: str
    date_from: date
    date_to: date
    notes: Sequence[SummaryNote]


@dataclass(frozen=True, slots=True)
class SummaryResult:
    """El resumen ejecutivo con su costo y procedencia.

    Attributes:
        text: Párrafos separados por una línea en blanco, sin Markdown.
        usage: Tokens gastados (suma de intentos, si hubo reintento).
        model: Modelo usado.
        prompt_version: Versión del prompt (``summary_v1``).
    """

    text: str
    usage: LLMUsage
    model: str
    prompt_version: str


class SummaryError(RuntimeError):
    """La IA no dio un resumen válido tras el reintento (el reporte sale sin él).

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


class SummarizerPort(Protocol):
    """La IA que escribe el resumen ejecutivo de un reporte (§15)."""

    @property
    def model(self) -> str:
        """Modelo que se usa."""
        ...

    @property
    def summary_prompt_version(self) -> str:
        """Versión del prompt del resumen (se guarda con el resumen)."""
        ...

    async def aclose(self) -> None:
        """Libera las conexiones al terminar."""
        ...

    async def summarize(self, request: SummaryRequest) -> SummaryResult:
        """Escribe el resumen ejecutivo a partir de los resúmenes de las notas.

        Args:
            request: Búsqueda y notas relevantes.

        Returns:
            El resumen con su costo.

        Raises:
            SummaryError: Si la respuesta no fue válida tras un reintento.
            ProviderError: Si la IA no respondió (red, 429, 5xx, llave).
        """
        ...


@dataclass(frozen=True, slots=True)
class EntityExtractionRequest:
    """Lo que se le manda a la IA para que proponga las entidades de una nota.

    Attributes:
        title: Título.
        text: Cuerpo recortado, o el fragmento si el texto ya se borró
            (``AnalyzedText``).
        published_at: Fecha de publicación, si se conoce.
    """

    title: str
    text: str
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class EntityExtractionResult:
    """Las entidades que propuso la IA, sin revisar todavía contra el texto.

    Attributes:
        proposals: Propuestas con la forma del esquema (``RawProposal``).
        usage: Tokens gastados (suma de intentos, si hubo reintento).
        model: Modelo usado.
        prompt_version: Versión del prompt (``entities_v1``).
    """

    proposals: tuple[RawProposal, ...]
    usage: LLMUsage
    model: str
    prompt_version: str


class EntityExtractionError(RuntimeError):
    """La IA no dio una respuesta válida tras el reintento (la nota queda ``failed``).

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


class EntityExtractorPort(Protocol):
    """La IA que propone las entidades de una nota de un caso (Fase 9.4)."""

    @property
    def model(self) -> str:
        """Modelo que se usa."""
        ...

    @property
    def entities_prompt_version(self) -> str:
        """Versión del prompt (llave de ``entity_extractions``: con otra, se vuelve a leer)."""
        ...

    async def aclose(self) -> None:
        """Libera las conexiones al terminar."""
        ...

    async def extract_entities(self, request: EntityExtractionRequest) -> EntityExtractionResult:
        """Propone las entidades que menciona una nota, cada una con su cita.

        Args:
            request: Título y texto de la nota.

        Returns:
            Las propuestas con su costo; el caso de uso las revisa contra el
            texto antes de guardarlas.

        Raises:
            EntityExtractionError: Si la respuesta no fue válida tras un reintento.
            ProviderError: Si la IA no respondió (red, 429, 5xx, llave).
        """
        ...


@dataclass(frozen=True, slots=True)
class ClassificationNote:
    """Una nota tal como se le da a la IA para clasificarla (F12.4, ADR-0029).

    Solo título y resumen (o fragmento): nunca el texto completo (§8).

    Attributes:
        article_id: Nota (la IA responde con este id).
        title: Título.
        summary: Resumen de la IA o fragmento del medio, si hay.
    """

    article_id: int
    title: str
    summary: str | None


@dataclass(frozen=True, slots=True)
class CategoryOption:
    """Una categoría del catálogo como se le explica a la IA.

    Attributes:
        name: Nombre exacto que debe responder.
        description: Qué entra en ella.
    """

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class ClassificationRequest:
    """Un lote de notas por clasificar.

    Attributes:
        notes: Notas del lote.
        categories: Catálogo activo, con «Otros».
        other: Nombre de la categoría de respaldo («Otros»).
    """

    notes: Sequence[ClassificationNote]
    categories: Sequence[CategoryOption]
    other: str


@dataclass(frozen=True, slots=True)
class ClassificationLabel:
    """Lo que respondió la IA para una nota.

    Attributes:
        article_id: Nota.
        category: Nombre de categoría que eligió (se valida contra el catálogo).
        raw_label: Etiqueta libre que propuso, o ``None``.
        authority: Quién actúa en el hecho (F12.5, ADR-0030), o ``None`` si
            la IA no lo dijo.
    """

    article_id: int
    category: str | None
    raw_label: str | None
    authority: Authority | None = None


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Las categorías de un lote con su costo y procedencia.

    Attributes:
        labels: Una por nota que respondió la IA (puede faltar alguna).
        usage: Tokens gastados (suma de intentos, si hubo reintento).
        model: Modelo usado.
        prompt_version: Versión del prompt (``classify_v2``).
    """

    labels: tuple[ClassificationLabel, ...]
    usage: LLMUsage
    model: str
    prompt_version: str


class ClassificationError(RuntimeError):
    """La IA no dio una clasificación válida tras reintentar.

    Attributes:
        usage: Tokens que se gastaron de todos modos.
    """

    def __init__(self, message: str, usage: LLMUsage) -> None:
        """Guarda el mensaje y lo que se gastó.

        Args:
            message: Qué falló.
            usage: Tokens gastados en los intentos.
        """
        super().__init__(message)
        self.usage = usage


class ClassifierPort(Protocol):
    """La IA que clasifica notas por categoría (F12.4, ADR-0029)."""

    @property
    def model(self) -> str:
        """Modelo que se usa."""
        ...

    @property
    def classify_prompt_version(self) -> str:
        """Versión del prompt de clasificación (se guarda con cada nota)."""
        ...

    async def classify(self, request: ClassificationRequest) -> ClassificationResult:
        """Clasifica un lote de notas.

        Args:
            request: Notas y catálogo.

        Returns:
            La categoría de cada nota, con su costo.

        Raises:
            ClassificationError: Si la respuesta no fue válida tras un reintento.
            ProviderError: Si la IA no respondió (red, 429, 5xx, llave).
        """
        ...
