"""Esquemas de entrada y salida de ``/api/v1/concepts``.

La entrada solo comprueba tipos y pone topes amplios contra peticiones
abusivas; las reglas de negocio (largos, repetidos, caracteres prohibidos)
las aplica el dominio, que responde con mensajes en español por campo.

No hace: no valida reglas de negocio.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.api.v1.schemas.regions import RegionDetailOut
from app.application.pagination import Page
from app.application.use_cases.concepts import ConceptInput, QueryPreview
from app.domain.concept import Concept, ConceptChanges
from app.domain.queries import SEARCH_LANGUAGE_LABEL, PlannedQuery
from app.domain.query_dialects import DIALECTS

# Topes de transporte, muy por encima de las reglas del dominio (80
# caracteres, 50 términos): solo evitan cuerpos gigantes.
_MAX_TEXT = 2_000
_MAX_ITEMS = 500


class ConceptIn(BaseModel):
    """Concepto nuevo, o borrador para "Probar concepto"."""

    name: str = Field(max_length=_MAX_TEXT, examples=["Ciberseguridad"])
    description: str = Field(default="", max_length=_MAX_TEXT)
    keywords: list[str] = Field(
        max_length=_MAX_ITEMS, examples=[["ciberataque", "hackeo", "filtración de datos"]]
    )
    exclude_terms: list[str] = Field(default_factory=list, max_length=_MAX_ITEMS)
    color: str = Field(max_length=_MAX_TEXT, examples=["#2E86DE"])
    is_active: bool = True

    def to_input(self) -> ConceptInput:
        """Convierte al dato que reciben los casos de uso.

        Returns:
            Los datos sin validar todavía.
        """
        return ConceptInput(
            name=self.name,
            description=self.description,
            keywords=tuple(self.keywords),
            exclude_terms=tuple(self.exclude_terms),
            color=self.color,
            is_active=self.is_active,
        )


class ConceptPatch(BaseModel):
    """Cambios parciales: solo los campos enviados cambian.

    Las listas se reemplazan completas (no se agregan elementos sueltos).
    """

    name: str | None = Field(default=None, max_length=_MAX_TEXT)
    description: str | None = Field(default=None, max_length=_MAX_TEXT)
    keywords: list[str] | None = Field(default=None, max_length=_MAX_ITEMS)
    exclude_terms: list[str] | None = Field(default=None, max_length=_MAX_ITEMS)
    color: str | None = Field(default=None, max_length=_MAX_TEXT)
    is_active: bool | None = None

    def to_changes(self) -> ConceptChanges:
        """Convierte a los cambios del dominio.

        Returns:
            Los cambios; ``None`` significa "no cambia".
        """
        return ConceptChanges(
            name=self.name,
            description=self.description,
            keywords=tuple(self.keywords) if self.keywords is not None else None,
            exclude_terms=tuple(self.exclude_terms) if self.exclude_terms is not None else None,
            color=self.color,
            is_active=self.is_active,
        )


class ConceptOut(BaseModel):
    """Concepto guardado."""

    id: int
    name: str
    description: str
    keywords: list[str]
    exclude_terms: list[str]
    color: str = Field(description="#RRGGBB")
    is_active: bool = Field(description="Si aparece en el panel de búsqueda.")
    created_by: str
    created_at: datetime
    updated_at: datetime
    category_id: int | None = Field(
        default=None,
        description=(
            "Si es el tema general de una subdivisión, su categoría (``/categories``); "
            "``null`` en la FGR y en los conceptos de cada analista."
        ),
    )

    @classmethod
    def from_domain(cls, concept: Concept) -> "ConceptOut":
        """Convierte un ``Concept`` del dominio.

        Args:
            concept: Concepto guardado.

        Returns:
            El esquema listo para serializar.
        """
        data = concept.data
        return cls(
            id=concept.id,
            name=data.name,
            description=data.description,
            keywords=list(data.keywords),
            exclude_terms=list(data.exclude_terms),
            color=data.color,
            is_active=data.is_active,
            created_by=concept.created_by,
            created_at=concept.created_at,
            updated_at=concept.updated_at,
            category_id=concept.category_id,
        )


class ConceptPageOut(BaseModel):
    """Página de conceptos con cursor (CLAUDE.md §6.3)."""

    items: list[ConceptOut]
    next_cursor: str | None = Field(description="Pásalo como ?cursor= para la siguiente página.")

    @classmethod
    def from_page(cls, page: Page[Concept]) -> "ConceptPageOut":
        """Convierte una página del caso de uso.

        Args:
            page: Página de conceptos.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            items=[ConceptOut.from_domain(c) for c in page.items], next_cursor=page.next_cursor
        )


class QueryFiltersOut(BaseModel):
    """Filtros que se aplican aparte del texto, en palabras."""

    country: str = Field(examples=["México"])
    language: str = Field(examples=["español"])
    period: str = Field(examples=["últimos 7 días"])


class PlannedQueryOut(BaseModel):
    """Una consulta que se enviaría a un proveedor."""

    provider: str = Field(examples=["searchapi"])
    provider_label: str = Field(examples=["SearchApi (Google News)"])
    text: str = Field(description="Texto exacto de la consulta.")
    keywords: list[str] = Field(description="Palabras clave que cubre esta consulta.")
    filters: QueryFiltersOut
    estimated_credits: int

    @classmethod
    def from_domain(cls, query: PlannedQuery) -> "PlannedQueryOut":
        """Convierte una ``PlannedQuery`` del dominio.

        Args:
            query: Consulta planeada.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            provider=query.provider.value,
            provider_label=DIALECTS[query.provider].label,
            text=query.text,
            keywords=list(query.keywords),
            filters=QueryFiltersOut(
                country=query.country.name,
                language=SEARCH_LANGUAGE_LABEL,
                period=query.window.describe(),
            ),
            estimated_credits=query.estimated_credits,
        )


class DateWindowOut(BaseModel):
    """Rango de fechas de la vista previa."""

    date_from: date
    date_to: date
    description: str = Field(examples=["últimos 7 días"])


class QueryPreviewOut(BaseModel):
    """Resultado de "Probar concepto": nada se envió ni gastó créditos."""

    concept_name: str
    region: RegionDetailOut
    window: DateWindowOut
    queries: list[PlannedQueryOut]
    total_queries: int
    total_credits: int = Field(description="Créditos estimados (solo SearchApi cobra).")

    @classmethod
    def from_preview(cls, preview: QueryPreview) -> "QueryPreviewOut":
        """Convierte el resultado del caso de uso.

        Args:
            preview: Vista previa.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            concept_name=preview.concept_name,
            region=RegionDetailOut.from_detail(preview.region),
            window=DateWindowOut(
                date_from=preview.window.date_from,
                date_to=preview.window.date_to,
                description=preview.window.describe(),
            ),
            queries=[PlannedQueryOut.from_domain(q) for q in preview.queries],
            total_queries=len(preview.queries),
            total_credits=preview.total_credits,
        )
