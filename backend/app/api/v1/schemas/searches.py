"""Esquemas de entrada y salida de ``/api/v1/searches`` (especificación §13).

La entrada solo comprueba tipos y pone topes de transporte; las reglas
(conceptos activos, rango de 1 a 90 días, presupuesto) las aplican el
dominio y los casos de uso, con mensajes en español.

No hace: no valida reglas de negocio.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.api.v1.schemas.concepts import PlannedQueryOut
from app.application.pagination import Page
from app.application.ports.search_reads import SearchDetail
from app.application.use_cases.plan_search import SearchEstimate
from app.domain.errors import InvalidRequestError
from app.domain.queries import DateWindow, Provider
from app.domain.search import SearchTrigger

# Tope de transporte: una búsqueda con más conceptos no cabría en el
# presupuesto de consultas de todos modos (MAX_QUERIES_PER_SEARCH).
_MAX_CONCEPTS = 20
# "Últimos 7 días": el rango de la historia H1.
DEFAULT_DAYS = 7


class SearchIn(BaseModel):
    """Qué buscar: conceptos, región y fechas (últimos N días o un rango fijo)."""

    concept_ids: list[int] = Field(
        min_length=1, max_length=_MAX_CONCEPTS, examples=[[3]], description="Conceptos."
    )
    region_id: int = Field(description="Región (``/regions``).", examples=[15])
    days: int = Field(
        default=DEFAULT_DAYS, description="Últimos N días (1 a 90). Se ignora con fechas fijas."
    )
    date_from: date | None = Field(default=None, description="Rango fijo: primer día.")
    date_to: date | None = Field(default=None, description="Rango fijo: último día.")
    providers: list[Provider] | None = Field(
        default=None,
        description=(
            "Fuentes encendidas (``/sources``). Sin mandar, las de por defecto; "
            "lista vacía o una fuente sin configurar responde 422."
        ),
        examples=[["google_news_rss", "indice_local"]],
    )
    category_ids: list[int] = Field(
        default_factory=list,
        max_length=_MAX_CONCEPTS,
        description=(
            "Subdivisiones (``/categories``) para los conceptos como la FGR: cada nota "
            "debe traer las palabras del concepto y las de una subdivisión."
        ),
        examples=[[5]],
    )

    def window(self, today: date) -> DateWindow:
        """Rango de fechas pedido.

        Args:
            today: Hoy en la Ciudad de México.

        Returns:
            El rango fijo si vienen las dos fechas; si no, los últimos días.

        Raises:
            InvalidRequestError: Si viene solo una de las dos fechas, o el
                rango no es válido.
        """
        if self.date_from is None and self.date_to is None:
            return DateWindow.last_days(self.days, today)
        if self.date_from is None or self.date_to is None:
            raise InvalidRequestError("Para un rango fijo manda date_from y date_to.")
        return DateWindow.between(self.date_from, self.date_to)


class ConceptRefOut(BaseModel):
    """Un concepto de la búsqueda."""

    id: int
    name: str = Field(examples=["Extorsión"])
    subdivision_ids: list[int] = Field(
        default_factory=list,
        description="Subdivisiones con que se buscó (``/categories``), p. ej. FGR + Homicidio.",
    )


class LLMEstimateOut(BaseModel):
    """La IA que se usaría y lo máximo que costaría."""

    provider: str = Field(examples=["openai"])
    model: str = Field(examples=["gpt-6-luna"])
    configured: bool = Field(description="Si tiene su llave; sin ella no se puede buscar.")
    max_articles: int = Field(description="Notas que se mandarían como máximo a la IA.")
    max_cost_usd: float = Field(
        description="Costo si se enriquece el máximo; las notas ya procesadas no se pagan."
    )


class EstimateOut(BaseModel):
    """Lo que haría una búsqueda y cuánto costaría, sin gastar nada."""

    concepts: list[ConceptRefOut]
    region_id: int
    region: str = Field(examples=["México › Jalisco"])
    date_from: date
    date_to: date
    queries: list[PlannedQueryOut]
    credits: int = Field(description="Créditos de SearchApi que se gastarían.")
    credits_month: int = Field(description="Créditos ya gastados este mes.")
    credits_limit: int = Field(description="Tope mensual de créditos.")
    over_limit: bool = Field(description="Si se pasaría el tope (la búsqueda no se podría lanzar).")
    llm: LLMEstimateOut
    providers: list[str] = Field(
        description="Fuentes con las que se buscaría.", examples=[["google_news_rss"]]
    )

    @classmethod
    def from_estimate(cls, estimate: SearchEstimate) -> "EstimateOut":
        """Convierte la estimación del caso de uso.

        Args:
            estimate: Resultado de ``PlanSearch``.

        Returns:
            El esquema listo para serializar.
        """
        search = estimate.search
        return cls(
            concepts=[
                ConceptRefOut(id=c.concept_id, name=c.name, subdivision_ids=list(c.category_ids))
                for c in search.concepts
            ],
            region_id=search.region_id,
            region=estimate.breadcrumb,
            date_from=search.date_from,
            date_to=search.date_to,
            queries=[PlannedQueryOut.from_domain(q) for q in estimate.queries],
            credits=estimate.credits,
            credits_month=estimate.credits_month,
            credits_limit=estimate.credits_limit,
            over_limit=estimate.over_limit,
            llm=LLMEstimateOut(
                provider=estimate.llm.provider,
                model=estimate.llm.model,
                configured=estimate.llm.configured,
                max_articles=estimate.llm_max_articles,
                max_cost_usd=round(estimate.llm_max_cost_usd, 4),
            ),
            providers=[p.value for p in search.providers],
        )


class SearchStartedOut(BaseModel):
    """Búsqueda lanzada: consulta su avance en ``GET /searches/{search_id}``."""

    search_id: str = Field(examples=["b01afb0d-e78b-4257-8a14-5d2e98082d83"])
    status: str = Field(examples=["pending"])
    estimate: EstimateOut


class SearchOut(BaseModel):
    """Una búsqueda: estado, avance y costo. La pantalla la consulta mientras corre."""

    search_id: str
    status: str = Field(
        examples=["running"], description="pending, running, completed, partial o failed."
    )
    region_id: int
    region_code: str = Field(examples=["14"])
    region_name: str = Field(examples=["Jalisco"])
    date_from: date
    date_to: date
    concepts: list[ConceptRefOut]
    progress: dict[str, object] = Field(
        description=(
            "Etapa actual (stage: query, dedupe, extract, enrich, geocode, filter, close) "
            "y conteos: articles, reused, enriched, fallback, in_region, out_of_region, unlocated."
        ),
        examples=[{"stage": "enrich", "articles": 18, "enriched": 10}],
    )
    queries_planned: int
    credits_estimated: int
    credits_used: int
    llm_tokens_in: int
    llm_tokens_out: int
    llm_cost_usd: float
    results_count: int = Field(description="Notas distintas encontradas.")
    error_summary: str | None = Field(description="Qué falló, si algo falló.")
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    providers: list[str] = Field(
        description=(
            "Fuentes con las que se hizo. Vacía en búsquedas de antes de F12.2, "
            "que usaron todas las configuradas."
        ),
        examples=[["google_news_rss", "indice_local"]],
    )
    trigger: SearchTrigger = Field(
        default=SearchTrigger.MANUAL,
        description=(
            "Quién la lanzó: manual (una persona) o automatic (el monitor FGR a las "
            "07:00, 15:00 o 23:00, ADR-0031). Las automáticas las ven todos."
        ),
    )
    scheduled_for: datetime | None = Field(
        default=None, description="Hora programada de una corrida automática (UTC)."
    )
    window_start: datetime | None = Field(
        default=None,
        description=(
            "Corridas automáticas: desde cuándo cubre (la corrida anterior). Solo cuentan las "
            "notas publicadas entre window_start y window_end. Vacío en las manuales."
        ),
    )
    window_end: datetime | None = Field(
        default=None, description="Corridas automáticas: hasta cuándo cubre (su hora)."
    )

    @classmethod
    def from_detail(cls, detail: SearchDetail) -> "SearchOut":
        """Convierte la búsqueda leída.

        Args:
            detail: Búsqueda del lector.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            search_id=str(detail.search_id),
            status=detail.status.value,
            region_id=detail.region_id,
            region_code=detail.region_code,
            region_name=detail.region_name,
            date_from=detail.date_from,
            date_to=detail.date_to,
            concepts=[
                ConceptRefOut(id=c.id, name=c.name, subdivision_ids=list(c.subdivision_ids))
                for c in detail.concepts
            ],
            progress=dict(detail.progress),
            queries_planned=detail.queries_planned,
            credits_estimated=detail.credits_estimated,
            credits_used=detail.credits_used,
            llm_tokens_in=detail.llm_usage.tokens_in,
            llm_tokens_out=detail.llm_usage.tokens_out,
            llm_cost_usd=detail.llm_cost_usd,
            results_count=detail.results_count,
            error_summary=detail.error_summary,
            created_at=detail.created_at,
            started_at=detail.started_at,
            finished_at=detail.finished_at,
            providers=list(detail.providers),
            trigger=detail.trigger,
            scheduled_for=detail.scheduled_for,
            window_start=detail.window_start,
            window_end=detail.window_end,
        )


class SearchPageOut(BaseModel):
    """Página del historial, de la más reciente a la más vieja (cursor, CLAUDE.md §6.3)."""

    items: list[SearchOut]
    next_cursor: str | None = Field(description="Pásalo como ?cursor= para la siguiente página.")

    @classmethod
    def from_page(cls, page: Page[SearchDetail]) -> "SearchPageOut":
        """Convierte una página del caso de uso.

        Args:
            page: Página de búsquedas.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            items=[SearchOut.from_detail(d) for d in page.items], next_cursor=page.next_cursor
        )
