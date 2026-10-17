"""Lanzar una búsqueda: validar, crearla en ``pending`` y mandarla al worker (§9, §13).

Lo usa ``POST /searches``. Antes de crear nada revisa que se pueda correr:

- que la IA elegida tenga su llave (si no, ``503 llm_not_configured``);
- que haya al menos un proveedor disponible;
- que no pase el máximo de consultas por búsqueda (``MAX_QUERIES_PER_SEARCH``);
- que no haga pasar el tope mensual de créditos (``409 credit_limit_reached``).

Si algo falla no se crea la búsqueda ni se gasta nada.

No hace: no corre la búsqueda (eso lo hace el worker con ``RunSearch``).
"""

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.search_queue import SearchQueuePort
from app.application.ports.search_store import SearchStorePort
from app.application.use_cases.plan_search import PlanSearch, SearchEstimate, SearchRequest
from app.domain.budget import check_query_count
from app.domain.errors import (
    CreditLimitReachedError,
    LLMNotConfiguredError,
    ServiceUnavailableError,
)


@dataclass(frozen=True, slots=True)
class StartedSearch:
    """Una búsqueda recién lanzada.

    Attributes:
        search_id: Id para consultar su avance.
        estimate: Lo que se planeó y su costo estimado.
    """

    search_id: UUID
    estimate: SearchEstimate


class StartSearch:
    """Crea la búsqueda y la encola si se puede correr."""

    def __init__(
        self,
        planner: PlanSearch,
        searches: SearchStorePort,
        queue: SearchQueuePort,
        max_queries: int,
    ) -> None:
        """Recibe las piezas.

        Args:
            planner: Planeación y costo.
            searches: Búsquedas guardadas.
            queue: Cola del worker.
            max_queries: ``MAX_QUERIES_PER_SEARCH``.
        """
        self._planner = planner
        self._searches = searches
        self._queue = queue
        self._max_queries = max_queries

    async def execute(self, request: SearchRequest) -> StartedSearch:
        """Lanza la búsqueda.

        Args:
            request: Conceptos, región y fechas.

        Returns:
            El id de la búsqueda y lo planeado.

        Raises:
            LLMNotConfiguredError: Si falta la llave de la IA.
            ServiceUnavailableError: Si no hay ningún proveedor disponible.
            QueryBudgetExceededError: Si planea más consultas de las permitidas.
            CreditLimitReachedError: Si pasaría el tope mensual de créditos.
            InvalidRequestError, ConceptNotFoundError, RegionNotFoundError:
                Ver ``PlanSearch.estimate``.
        """
        estimate = await self._planner.estimate(request)
        if not estimate.llm.configured:
            raise LLMNotConfiguredError(
                f"La IA ({estimate.llm.provider}) no tiene su llave configurada; "
                "avisa a quien administra el sistema.",
                {"proveedor": estimate.llm.provider},
            )
        if not estimate.queries:
            raise ServiceUnavailableError("No hay ningún proveedor de noticias disponible.")
        check_query_count(len(estimate.queries), self._max_queries)
        if estimate.over_limit:
            raise CreditLimitReachedError(
                "Esta búsqueda pasaría el tope mensual de créditos de SearchApi.",
                {
                    "creditos": estimate.credits,
                    "usados_en_el_mes": estimate.credits_month,
                    "tope": estimate.credits_limit,
                },
            )
        search_id = await self._searches.create(estimate.search)
        self._queue.enqueue(search_id)
        return StartedSearch(search_id, estimate)
