"""Planear una búsqueda y estimar su costo antes de gastar (§9 paso 1; ADR-0015).

Lo usan ``POST /searches/estimate``, ``POST /searches`` y ``make buscar``,
para que la pantalla y la terminal den siempre los mismos números:

- las consultas que se harían, con los conceptos y la región guardados;
- los créditos de SearchApi, lo ya gastado en el mes y su tope;
- el costo máximo de la IA (``LLM_MAX_ARTICLES_PER_SEARCH`` notas con la
  tarifa del modelo elegido). Lo real suele ser menor: las notas ya
  procesadas no se pagan.

No hace: no crea la búsqueda ni consulta a nadie (``ExecuteQueries`` y
``RunSearch`` lo hacen después).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.clock import MEXICO_CITY
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.llm import LLMInfo
from app.application.ports.provider_log import ProviderQueryLogPort
from app.application.ports.providers import NewsProviderPort
from app.application.ports.regions import RegionRepositoryPort
from app.application.ports.search_store import NewSearch, SearchConcept
from app.application.use_cases.run_search import plan_queries
from app.domain.budget import month_start
from app.domain.enrichment import estimated_usage
from app.domain.errors import (
    ConceptNotFoundError,
    InvalidRequestError,
    RegionNotFoundError,
)
from app.domain.queries import DateWindow, PlannedQuery, Provider, place_for
from app.domain.sources import resolve_sources


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Lo que pide quien busca.

    Attributes:
        user_id: Quién busca.
        concept_ids: Conceptos (al menos uno, sin repetir).
        region_id: Región.
        window: Rango de fechas.
        providers: Fuentes que encendió el analista (switches, ADR-0027), o
            ``None`` para usar las de por defecto.
    """

    user_id: str
    concept_ids: tuple[int, ...]
    region_id: int
    window: DateWindow
    providers: tuple[Provider, ...] | None = None


@dataclass(frozen=True, slots=True)
class SearchEstimate:
    """La búsqueda armada y lo que costaría.

    Attributes:
        search: Datos para crear la fila de ``searches``.
        breadcrumb: Región elegida ("México › Jalisco").
        queries: Consultas que se enviarían.
        credits: Créditos de SearchApi estimados.
        credits_month: Créditos ya gastados este mes.
        credits_limit: Tope mensual (``SEARCHAPI_MONTHLY_CREDIT_LIMIT``).
        llm: IA que se usaría y su tarifa.
        llm_max_articles: Tope de notas para la IA.
        llm_max_cost_usd: Costo si se enriquece el tope completo.
    """

    search: NewSearch
    breadcrumb: str
    queries: tuple[PlannedQuery, ...]
    credits: int
    credits_month: int
    credits_limit: int
    llm: LLMInfo
    llm_max_articles: int
    llm_max_cost_usd: float

    @property
    def over_limit(self) -> bool:
        """``True`` si las consultas pasarían el tope mensual de créditos."""
        return self.credits_month + self.credits > self.credits_limit


class PlanSearch:
    """Arma una búsqueda con los datos guardados y calcula su costo."""

    def __init__(  # noqa: PLR0913 — una dependencia por dato de la estimación, todo por nombre (*)
        self,
        *,
        concepts: ConceptRepositoryPort,
        regions: RegionRepositoryPort,
        providers: Mapping[Provider, NewsProviderPort],
        log: ProviderQueryLogPort,
        llm: LLMInfo,
        llm_max_articles: int,
        credits_limit: int,
        default_sources: Sequence[Provider] = tuple(Provider),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Recibe las piezas.

        Args:
            concepts: Conceptos guardados.
            regions: Catálogo.
            providers: Proveedores; solo se planea con los configurados.
            log: Registro de peticiones (créditos del mes).
            llm: IA elegida y su tarifa.
            llm_max_articles: ``LLM_MAX_ARTICLES_PER_SEARCH``.
            credits_limit: ``SEARCHAPI_MONTHLY_CREDIT_LIMIT``.
            default_sources: Fuentes encendidas si el analista no elige
                (``MANUAL_DEFAULT_SOURCES``); por defecto, todas.
            now: Reloj (las pruebas lo fijan).
        """
        self._concepts = concepts
        self._regions = regions
        self._providers = providers
        self._log = log
        self._llm = llm
        self._llm_max_articles = llm_max_articles
        self._credits_limit = credits_limit
        self._default_sources = tuple(default_sources)
        self._now = now

    def available_providers(self) -> tuple[Provider, ...]:
        """Proveedores con los que se planea de verdad, en su orden.

        Los que no están configurados (sin llave, o apagados como GDELT,
        ADR-0012, o el RSS de Google si se apaga, ADR-0021) no reciben
        consultas. "Probar concepto" usa esta misma lista para mostrar lo que
        una búsqueda mandaría.

        Returns:
            Los proveedores configurados.
        """
        return tuple(p for p, adapter in self._providers.items() if adapter.is_configured())

    async def _concepts_of(self, ids: Sequence[int]) -> tuple[SearchConcept, ...]:
        if not ids:
            raise InvalidRequestError("Elige al menos un concepto.")
        if len(set(ids)) != len(ids):
            raise InvalidRequestError("Un concepto está repetido.", {"concept_ids": list(ids)})
        found = []
        for concept_id in ids:
            concept = await self._concepts.get(concept_id)
            if concept is None:
                raise ConceptNotFoundError("No existe ese concepto.", {"id": concept_id})
            if not concept.data.is_active:
                raise InvalidRequestError(
                    f'El concepto "{concept.data.name}" está desactivado.', {"id": concept_id}
                )
            data = concept.data
            found.append(
                SearchConcept(
                    concept.id, data.name, data.description, data.keywords, data.exclude_terms
                )
            )
        return tuple(found)

    async def estimate(self, request: SearchRequest) -> SearchEstimate:
        """Planea la búsqueda sin gastar nada.

        Args:
            request: Conceptos, región y fechas.

        Returns:
            Las consultas y el costo.

        Raises:
            InvalidRequestError: Sin conceptos, con conceptos repetidos o
                desactivados, sin fuentes o con una fuente no configurada.
            ConceptNotFoundError: Si un concepto no existe o fue borrado.
            RegionNotFoundError: Si la región no existe.
            QueryTooLongError: Si una palabra clave no cabe en un proveedor.
        """
        concepts = await self._concepts_of(request.concept_ids)
        region = await self._regions.get(request.region_id)
        facts = await self._regions.place_facts(request.region_id) if region else None
        if region is None or facts is None:
            raise RegionNotFoundError("No existe esa región.", {"id": request.region_id})
        ancestors = await self._regions.ancestors(region.id)
        available = self.available_providers()
        # Sin ningún proveedor configurado no hay nada que elegir: StartSearch
        # responde «no hay proveedores disponibles» (503), como antes de F12.2.
        sources = (
            resolve_sources(request.providers, self._default_sources, available)
            if available
            else ()
        )
        queries = tuple(plan_queries(concepts, place_for(facts), request.window, sources))
        credits_estimated = sum(self._providers[q.provider].estimate_cost(q) for q in queries)
        used = await self._log.credits_used_since(
            Provider.SEARCHAPI.value, month_start(self._now(), MEXICO_CITY)
        )
        window = request.window
        return SearchEstimate(
            search=NewSearch(
                user_id=request.user_id,
                region_id=region.id,
                date_from=window.date_from,
                date_to=window.date_to,
                concepts=concepts,
                queries_planned=len(queries),
                credits_estimated=credits_estimated,
                providers=sources,
            ),
            breadcrumb=" › ".join([*(a.name for a in ancestors), region.name]),
            queries=queries,
            credits=credits_estimated,
            credits_month=used,
            credits_limit=self._credits_limit,
            llm=self._llm,
            llm_max_articles=self._llm_max_articles,
            llm_max_cost_usd=estimated_usage(self._llm_max_articles).cost_usd(
                self._llm.price_input_per_million, self._llm.price_output_per_million
            ),
        )
