"""Revisar la relevancia de una búsqueda ya hecha, sin escribir nada (ADR-0114).

Para medir si la relevancia estricta funciona hay que ver, en una búsqueda
real, qué pidió el analista, qué se descartó antes de la IA y cómo quedó cada
nota. Este caso de uso lo junta todo:

- el pedido: lo que escribió el analista, sus frases, los términos
  obligatorios y la región;
- los contadores del avance (``progress``): ``off_topic``, ``off_core`` con
  sus títulos de muestra, ``outside_window``, ``skipped_by_cap``…;
- una fila por nota con su banda (relevante, por confirmar, cercana, ajena o
  sin juicio), su puntaje, si cae en la región, cómo se leyó su texto, quién
  la encontró, el título y la razón de la IA. Van de la banda más alta a la
  más baja y, dentro de cada banda, del puntaje más alto al más bajo.

Lo usa ``make revisar-relevancia`` (``app/cli/revisar_relevancia.py``).

No hace: no escribe, no vuelve a juzgar ni llama a la IA o a los proveedores.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.application.pagination import TimeCursor
from app.application.ports.relevance_review import (
    SearchArticlesReaderPort,
    SearchCopyReaderPort,
)
from app.application.ports.search_reads import (
    ArticleFilters,
    ArticleItem,
    InRegion,
    JudgementView,
    SearchDetail,
)
from app.application.ports.search_store import SearchConcept
from app.application.use_cases.run_search import SearchNotFoundError
from app.domain.authority import RelevanceBand

# Notas por página al leer la búsqueda: el tope de la API (200) y de sobra
# para una búsqueda típica (120 a 300 notas) en una o dos vueltas.
REVIEW_PAGE_SIZE = 200
# Orden de las bandas en la revisión; ``None`` = la IA no la juzgó (pasó del
# tope por búsqueda o la IA falló).
BAND_ORDER: tuple[RelevanceBand | None, ...] = (
    RelevanceBand.RELEVANT,
    RelevanceBand.UNCONFIRMED,
    RelevanceBand.RELATED,
    RelevanceBand.UNRELATED,
    None,
)


@dataclass(frozen=True, slots=True)
class ReviewRow:
    """Una nota en la revisión.

    Attributes:
        article_id: Nota.
        band: Su mejor banda entre los conceptos, o ``None`` si no tiene juicio.
        score: Puntaje de ese juicio, o ``None``.
        concept: Concepto de ese juicio, o ``None``.
        in_region: Si cae en la región (``None``: sin ubicación).
        extraction_status: ``ok`` o ``fallback`` (solo título y fragmento).
        providers: Quién la encontró en esta búsqueda.
        title: Título.
        reason: Razón de la IA (o la de la regla FGR), si hay.
    """

    article_id: int
    band: RelevanceBand | None
    score: float | None
    concept: str | None
    in_region: bool | None
    extraction_status: str
    providers: tuple[str, ...]
    title: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class RelevanceReview:
    """Todo lo que se revisa de una búsqueda.

    Attributes:
        detail: Región, avance y costos.
        concepts: Conceptos copiados (lo que pidió el analista).
        rows: Una fila por nota, ordenadas por banda y puntaje.
    """

    detail: SearchDetail
    concepts: tuple[SearchConcept, ...]
    rows: tuple[ReviewRow, ...]

    @property
    def progress(self) -> Mapping[str, object]:
        """Contadores del avance (``searches.progress``)."""
        return self.detail.progress

    def band_counts(self) -> dict[RelevanceBand | None, int]:
        """Cuántas notas hay en cada banda (``None`` = sin juicio), en ``BAND_ORDER``."""
        return {band: sum(1 for r in self.rows if r.band is band) for band in BAND_ORDER}

    def outside_region(self) -> int:
        """Cuántas notas caen fuera de la región."""
        return sum(1 for r in self.rows if r.in_region is False)


def _rank(judgement: JudgementView) -> tuple[int, float]:
    band = judgement.band
    return BAND_ORDER.index(band), -judgement.relevance_score


def review_row(item: ArticleItem) -> ReviewRow:
    """La fila de una nota: su mejor juicio entre los conceptos de la búsqueda.

    Args:
        item: Nota leída, con los juicios ya con la regla de su concepto.

    Returns:
        La fila.
    """
    best = min(item.judgements, key=_rank) if item.judgements else None
    return ReviewRow(
        article_id=item.article_id,
        band=best.band if best else None,
        score=best.relevance_score if best else None,
        concept=best.name if best else None,
        in_region=item.in_region,
        extraction_status=item.extraction_status,
        providers=item.providers,
        title=item.title,
        reason=best.relevance_reason if best else None,
    )


def ordered(rows: Sequence[ReviewRow]) -> tuple[ReviewRow, ...]:
    """Las filas de la banda más alta a la más baja y, en cada una, por puntaje.

    Args:
        rows: Filas en cualquier orden.

    Returns:
        Ordenadas; en empate, por título.
    """
    return tuple(
        sorted(
            rows,
            key=lambda r: (
                BAND_ORDER.index(r.band),
                -(r.score if r.score is not None else 0.0),
                r.title,
            ),
        )
    )


class ReviewRelevance:
    """Junta el pedido, los contadores y las notas de una búsqueda, sin escribir."""

    def __init__(self, searches: SearchCopyReaderPort, articles: SearchArticlesReaderPort) -> None:
        """Recibe las lecturas.

        Args:
            searches: La búsqueda copiada y su avance.
            articles: Sus notas con los juicios.
        """
        self._searches = searches
        self._articles = articles

    async def execute(self, search_id: UUID | None = None) -> RelevanceReview:
        """Arma la revisión.

        Args:
            search_id: Búsqueda; ``None`` = la más reciente.

        Returns:
            La revisión.

        Raises:
            SearchNotFoundError: Si no hay búsquedas o no existe la pedida.
        """
        chosen = search_id or await self._searches.last_search_id()
        if chosen is None:
            raise SearchNotFoundError("No hay búsquedas todavía.")
        search = await self._searches.load(chosen)
        detail = await self._searches.search_detail(chosen)
        if search is None or detail is None:
            raise SearchNotFoundError(f"No existe la búsqueda {chosen}.")
        items = await self._all_articles(chosen)
        return RelevanceReview(detail, search.concepts, ordered([review_row(i) for i in items]))

    async def _all_articles(self, search_id: UUID) -> list[ArticleItem]:
        """Todas las notas de la búsqueda (relevantes o no, de cualquier región), por páginas."""
        filters = ArticleFilters(relevant_only=False, in_region=InRegion.ALL)
        items: list[ArticleItem] = []
        after: TimeCursor | None = None
        while True:
            page = await self._articles.search_articles(search_id, filters, after, REVIEW_PAGE_SIZE)
            items.extend(page)
            if len(page) < REVIEW_PAGE_SIZE:
                return items
            after = TimeCursor(page[-1].published_at, str(page[-1].article_id))
