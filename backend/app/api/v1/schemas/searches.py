"""Esquemas de entrada y salida de ``/api/v1/searches`` (especificación §13).

La entrada solo comprueba tipos y pone topes de transporte; las reglas
(conceptos activos, rango de 1 a 90 días, presupuesto) las aplican el
dominio y los casos de uso, con mensajes en español.

No hace: no valida reglas de negocio.
"""

from datetime import date

from pydantic import BaseModel, Field

from app.api.v1.schemas.concepts import PlannedQueryOut
from app.application.use_cases.plan_search import SearchEstimate
from app.domain.errors import InvalidRequestError
from app.domain.queries import DateWindow

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
            concepts=[ConceptRefOut(id=c.concept_id, name=c.name) for c in search.concepts],
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
        )


class SearchStartedOut(BaseModel):
    """Búsqueda lanzada: consulta su avance en ``GET /searches/{search_id}``."""

    search_id: str = Field(examples=["b01afb0d-e78b-4257-8a14-5d2e98082d83"])
    status: str = Field(examples=["pending"])
    estimate: EstimateOut
