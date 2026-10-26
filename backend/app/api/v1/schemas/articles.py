"""Esquemas de salida de las notas (``/searches/{id}/articles`` y ``/articles/{id}``).

De cada nota se entregan metadatos, el resumen propio de la IA, sus
conceptos, su ubicación y el link al medio. **Nunca el texto completo**
(CLAUDE.md §8).

No hace: no valida reglas de negocio.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.application.pagination import Page
from app.application.ports.search_reads import (
    ArticleDetail,
    ArticleItem,
    CategoryView,
    JudgementView,
    LocationView,
)
from app.application.use_cases.search_reads import AggregatesView
from app.domain.authority import Authority


class JudgementOut(BaseModel):
    """Lo que dijo la IA de la nota para un concepto."""

    concept_id: int
    name: str = Field(examples=["Extorsión"])
    is_relevant: bool
    relevance_score: float = Field(ge=0, le=1)
    relevance_reason: str | None

    @classmethod
    def from_view(cls, view: JudgementView) -> "JudgementOut":
        """Convierte el juicio leído.

        Args:
            view: Juicio del lector.

        Returns:
            El esquema.
        """
        return cls(
            concept_id=view.concept_id,
            name=view.name,
            is_relevant=view.is_relevant,
            relevance_score=view.relevance_score,
            relevance_reason=view.relevance_reason,
        )


class LocationOut(BaseModel):
    """Un lugar de la nota resuelto contra el catálogo INEGI (§11)."""

    mention: str = Field(examples=["Guadalajara"], description="Cómo lo nombra la nota.")
    role: str = Field(
        examples=["event"], description="event: donde pasó; mentioned: solo se nombra."
    )
    precision: str = Field(examples=["municipality"])
    confidence: float = Field(ge=0, le=1)
    is_primary: bool = Field(description="Si es la ubicación que se pinta en el mapa.")
    region_id: int | None
    region_code: str | None = Field(examples=["14039"])
    place: str | None = Field(examples=["Municipio Guadalajara"])
    lon: float | None = Field(description="Punto del catálogo, nunca de la IA.")
    lat: float | None

    @classmethod
    def from_view(cls, view: LocationView) -> "LocationOut":
        """Convierte la ubicación leída.

        Args:
            view: Ubicación del lector.

        Returns:
            El esquema.
        """
        return cls(
            mention=view.mention,
            role=view.role,
            precision=view.precision,
            confidence=round(view.confidence, 2),
            is_primary=view.is_primary,
            region_id=view.region_id,
            region_code=view.region_code,
            place=view.place,
            lon=view.lon,
            lat=view.lat,
        )


class CategoryOut(BaseModel):
    """El delito del que trata una nota (F12.4, ADR-0029)."""

    id: int
    name: str = Field(examples=["Armas y explosivos"])
    color: str | None = Field(default=None, description="Se define después, con datos reales.")
    symbol: str | None = Field(default=None, description="Se define después, con datos reales.")

    @classmethod
    def from_view(cls, view: CategoryView) -> "CategoryOut":
        """Convierte la categoría leída.

        Args:
            view: Categoría.

        Returns:
            El esquema.
        """
        return cls(id=view.category_id, name=view.name, color=view.color, symbol=view.symbol)


class ArticleOut(BaseModel):
    """Una nota en la lista de resultados."""

    article_id: int
    title: str
    source_name: str | None = Field(examples=["El Informador"])
    source_domain: str | None = Field(examples=["informador.mx"])
    url: str = Field(description="Link a la nota en el medio.")
    published_at: datetime | None
    summary: str | None = Field(description="Resumen propio de la IA, nunca el artículo.")
    event_type: str | None = Field(examples=["detención"])
    event_date: date | None
    extraction_status: str = Field(
        description="ok: se leyó el texto; fallback: solo título y fragmento."
    )
    enrichment_status: str = Field(description="ok, pending o failed.")
    concepts: list[JudgementOut]
    primary_location: LocationOut | None = Field(
        description="La que se pinta; null = sin ubicación."
    )
    in_region: bool | None = Field(description="true dentro, false fuera, null sin ubicación.")
    providers: list[str] = Field(examples=[["searchapi", "indice_local"]])
    story_id: int | None = Field(
        default=None,
        description=(
            "Historia: id de la primera nota del mismo hecho en varios medios; "
            "null si la nota está sola (ADR-0026)."
        ),
    )

    category: CategoryOut | None = Field(
        default=None, description="El delito del que trata; null si falta clasificarla."
    )
    category_raw: str | None = Field(
        default=None,
        description="Etiqueta libre que propuso la IA (para afinar las categorías después).",
        examples=["tráfico de armas"],
    )
    authority: Authority | None = Field(
        default=None,
        description=(
            "Quién actúa en el hecho según la IA: fgr, fgr_mencion, estatal, otra o "
            "sin_dato; null si falta clasificarla. En los conceptos con la regla "
            "«FGR federal» la relevancia ya lo toma en cuenta (ADR-0030)."
        ),
        examples=["estatal"],
    )

    @classmethod
    def from_item(cls, item: ArticleItem) -> "ArticleOut":
        """Convierte la nota leída.

        Args:
            item: Nota del lector.

        Returns:
            El esquema.
        """
        return cls(
            article_id=item.article_id,
            title=item.title,
            source_name=item.source_name,
            source_domain=item.source_domain,
            url=item.url,
            published_at=item.published_at,
            summary=item.summary,
            event_type=item.event_type,
            event_date=item.event_date,
            extraction_status=item.extraction_status,
            enrichment_status=item.enrichment_status,
            concepts=[JudgementOut.from_view(j) for j in item.judgements],
            primary_location=LocationOut.from_view(item.primary) if item.primary else None,
            in_region=item.in_region,
            providers=list(item.providers),
            story_id=item.story_id,
            category=CategoryOut.from_view(item.category) if item.category else None,
            category_raw=item.category_raw,
            authority=item.authority,
        )


class ArticlePageOut(BaseModel):
    """Página de notas, de la más reciente a la más vieja (cursor, CLAUDE.md §6.3)."""

    items: list[ArticleOut]
    next_cursor: str | None = Field(description="Pásalo como ?cursor= para la siguiente página.")

    @classmethod
    def from_page(cls, page: Page[ArticleItem]) -> "ArticlePageOut":
        """Convierte una página del caso de uso.

        Args:
            page: Página de notas.

        Returns:
            El esquema.
        """
        return cls(
            items=[ArticleOut.from_item(i) for i in page.items], next_cursor=page.next_cursor
        )


class ArticleDetailOut(ArticleOut):
    """Una nota con todas sus menciones de lugar (nunca el texto completo)."""

    locations: list[LocationOut]
    first_seen_at: datetime
    llm_model: str | None = Field(examples=["gpt-6-luna"])
    prompt_version: str | None = Field(examples=["enrich_v2"])

    @classmethod
    def from_detail(cls, detail: ArticleDetail) -> "ArticleDetailOut":
        """Convierte la nota leída.

        Args:
            detail: Nota del lector.

        Returns:
            El esquema.
        """
        return cls(
            **ArticleOut.from_item(detail.item).model_dump(),
            locations=[LocationOut.from_view(loc) for loc in detail.locations],
            first_seen_at=detail.first_seen_at,
            llm_model=detail.llm_model,
            prompt_version=detail.prompt_version,
        )


class AggregateItemOut(BaseModel):
    """Una región del mapa de calor."""

    region_id: int
    code: str = Field(examples=["14"])
    name: str = Field(examples=["Jalisco"])
    count: int = Field(description="Notas cuya ubicación principal cae aquí.")
    lon: float = Field(description="Centro de la región.")
    lat: float


class CategoryCountOut(BaseModel):
    """Cuántas notas hay en una categoría."""

    category: CategoryOut | None = Field(description="null = notas todavía sin clasificar.")
    count: int


class AggregatesOut(BaseModel):
    """Conteo de notas por región, para el mapa de calor."""

    level: str = Field(examples=["state"])
    items: list[AggregateItemOut] = Field(description="De la región con más notas a la de menos.")
    coarser: int = Field(
        description="Notas con ubicación menos precisa que el nivel (no se reparten)."
    )
    abroad: int = Field(description="Notas de otro país (en los niveles de México).")
    unlocated: int = Field(description="Notas sin ubicación.")
    total: int
    by_category: list[CategoryCountOut] = Field(
        default_factory=list, description="Notas por categoría, de la que más tiene a la que menos."
    )

    @classmethod
    def from_view(cls, view: AggregatesView) -> "AggregatesOut":
        """Convierte el resultado del caso de uso.

        Args:
            view: Conteos.

        Returns:
            El esquema.
        """
        return cls(
            level=view.level.value,
            items=[
                AggregateItemOut(
                    region_id=i.region.region_id,
                    code=i.region.code,
                    name=i.region.name,
                    count=i.count,
                    lon=i.region.lon,
                    lat=i.region.lat,
                )
                for i in view.items
            ],
            coarser=view.coarser,
            abroad=view.abroad,
            unlocated=view.unlocated,
            total=view.total,
            by_category=[
                CategoryCountOut(
                    category=CategoryOut.from_view(c.category) if c.category else None,
                    count=c.count,
                )
                for c in view.by_category
            ],
        )
