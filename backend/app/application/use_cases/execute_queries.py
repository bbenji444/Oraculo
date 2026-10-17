"""Ejecutar las consultas de una búsqueda (paso 2 del pipeline, especificación §9).

Recibe las consultas ya planeadas (``build_queries``) y, para cada una:

1. **Presupuesto.** Si la búsqueda planea más de ``MAX_QUERIES_PER_SEARCH``
   consultas, se rechaza completa **antes** de enviar nada.
2. **Proveedor disponible.** Si no está configurado (SearchApi sin llave) o
   está desactivado (Google News RSS, ADR-0011; GDELT, ADR-0012), la
   consulta se registra como ``skipped`` con el motivo.
3. **Caché.** Una consulta idéntica reciente se responde desde la caché: no
   se envía ni cuesta créditos. El índice local no usa caché: cambia cada
   15 minutos y consultarlo es gratis (ADR-0013).
4. **Tope mensual.** Si una consulta de pago haría pasar el tope de
   créditos del mes, se salta.
5. **Envío y registro.** Cada consulta queda en ``provider_queries``.

Que falle un proveedor no tumba la búsqueda (§8): el resultado es
``partial`` y dice qué falló.

No hace: no deduplica, no lee las notas ni las guarda (pasos 3 en adelante,
F4).
"""

import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from app.application.clock import MEXICO_CITY
from app.application.ports.provider_log import (
    ProviderQueryLogPort,
    ProviderQueryRecord,
    QueryStatus,
)
from app.application.ports.providers import NewsProviderPort
from app.application.ports.query_cache import QueryCachePort, cache_key
from app.domain.articles import RawArticle
from app.domain.budget import MonthlyCredits, check_query_count, month_start
from app.domain.errors import ProviderError
from app.domain.queries import PlannedQuery, Provider
from app.domain.query_dialects import DIALECTS

_MS_PER_SECOND = 1000
_SECONDS_PER_HOUR = 3600


class ExecutionStatus(StrEnum):
    """Cómo terminó la ejecución de las consultas de una búsqueda."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """Qué pasó con una consulta.

    Attributes:
        query: La consulta.
        status: ``ok``, ``error`` o ``skipped``.
        articles: Notas que devolvió (vacío si no se envió o falló).
        from_cache: Si se respondió desde la caché.
        credits: Créditos gastados.
        message: Motivo en español si falló o se saltó.
    """

    query: PlannedQuery
    status: QueryStatus
    articles: tuple[RawArticle, ...] = ()
    from_cache: bool = False
    credits: int = 0
    message: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Resultado de ejecutar todas las consultas de una búsqueda.

    Attributes:
        outcomes: Una entrada por consulta, en el orden recibido.
    """

    outcomes: tuple[QueryOutcome, ...]

    @property
    def articles(self) -> tuple[RawArticle, ...]:
        """Todas las notas de las consultas exitosas (sin deduplicar)."""
        return tuple(a for o in self.outcomes for a in o.articles)

    @property
    def credits_used(self) -> int:
        """Créditos gastados en total."""
        return sum(o.credits for o in self.outcomes)

    @property
    def status(self) -> ExecutionStatus:
        """Estado global de la ejecución.

        ``completed`` si todo salió bien; ``partial`` si algo falló o se
        saltó pero al menos una consulta respondió; ``failed`` si ninguna.
        """
        ok = sum(1 for o in self.outcomes if o.status == "ok")
        if ok == len(self.outcomes):
            return ExecutionStatus.COMPLETED
        return ExecutionStatus.PARTIAL if ok else ExecutionStatus.FAILED


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Límites configurables de la ejecución (``.env``).

    Attributes:
        max_queries: ``MAX_QUERIES_PER_SEARCH``.
        cache_ttl_hours: ``QUERY_CACHE_TTL_HOURS`` (0 = sin caché).
        monthly_credit_limits: Tope mensual de créditos por proveedor de pago
            (``SEARCHAPI_MONTHLY_CREDIT_LIMIT``).
    """

    max_queries: int
    cache_ttl_hours: float
    monthly_credit_limits: Mapping[Provider, int]


class ExecuteQueries:
    """Envía las consultas planeadas con presupuesto, caché y registro."""

    def __init__(
        self,
        providers: Mapping[Provider, NewsProviderPort],
        cache: QueryCachePort,
        log: ProviderQueryLogPort,
        limits: ExecutionLimits,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Recibe los adaptadores y los límites.

        Args:
            providers: Adaptador de cada proveedor.
            cache: Caché de consultas.
            log: Registro de peticiones.
            limits: Límites de la configuración.
            now: Reloj (las pruebas lo fijan).
        """
        self._providers = providers
        self._cache = cache
        self._log = log
        self._limits = limits
        self._now = now

    async def execute(
        self, queries: Sequence[PlannedQuery], search_id: UUID | None = None
    ) -> ExecutionResult:
        """Ejecuta las consultas.

        Args:
            queries: Consultas planeadas (``build_queries``).
            search_id: Búsqueda a la que pertenecen (para el registro).

        Returns:
            Qué pasó con cada consulta y el estado global.

        Raises:
            QueryBudgetExceededError: Si son más de las permitidas; en ese
                caso no se envía nada.
        """
        check_query_count(len(queries), self._limits.max_queries)
        since = month_start(self._now(), MEXICO_CITY)
        budgets: dict[Provider, MonthlyCredits] = {}
        for provider, limit in self._limits.monthly_credit_limits.items():
            used = await self._log.credits_used_since(provider.value, since)
            budgets[provider] = MonthlyCredits(used=used, limit=limit)
        outcomes = await asyncio.gather(
            *(self._run_one(query, budgets, search_id) for query in queries)
        )
        return ExecutionResult(tuple(outcomes))

    async def _record(
        self,
        outcome: QueryOutcome,
        params: Mapping[str, str],
        search_id: UUID | None,
        *,
        started: float,
        http_status: int | None = None,
    ) -> QueryOutcome:
        query = outcome.query
        await self._log.record(
            ProviderQueryRecord(
                provider=query.provider.value,
                query_text=query.text,
                params=params,
                status=outcome.status,
                http_status=http_status,
                results_count=len(outcome.articles),
                from_cache=outcome.from_cache,
                cost_credits=outcome.credits,
                duration_ms=int((time.perf_counter() - started) * _MS_PER_SECOND),
                error_message=outcome.message,
                search_id=search_id,
            )
        )
        return outcome

    async def _run_one(
        self,
        query: PlannedQuery,
        budgets: Mapping[Provider, MonthlyCredits],
        search_id: UUID | None,
    ) -> QueryOutcome:
        started = time.perf_counter()
        provider = self._providers.get(query.provider)
        if provider is None or not provider.is_configured():
            outcome = QueryOutcome(
                query, "skipped", message=f"{query.provider.value} no está habilitado."
            )
            return await self._record(outcome, {}, search_id, started=started)
        params = provider.request_params(query)
        key = cache_key(query.provider.value, query.text, params)
        cacheable = DIALECTS[query.provider].cacheable
        cached = await self._cache.get(key) if cacheable else None
        if cached is not None:
            outcome = QueryOutcome(query, "ok", cached, from_cache=True)
            return await self._record(outcome, params, search_id, started=started)
        cost = provider.estimate_cost(query)
        monthly = budgets.get(query.provider)
        if cost and monthly is not None and not monthly.try_reserve(cost):
            outcome = QueryOutcome(
                query,
                "skipped",
                message=(
                    f"Se alcanzó el tope mensual de créditos de {query.provider.value} "
                    f"({monthly.limit})."
                ),
            )
            return await self._record(outcome, params, search_id, started=started)
        try:
            response = await provider.search(query)
        except ProviderError as error:
            if monthly is not None:
                # SearchApi solo cobra respuestas 200: un error no gasta créditos.
                monthly.release(cost)
            outcome = QueryOutcome(query, "error", message=error.message)
            return await self._record(
                outcome, params, search_id, started=started, http_status=error.http_status
            )
        ttl = int(self._limits.cache_ttl_hours * _SECONDS_PER_HOUR)
        if cacheable:
            await self._cache.set(key, response.articles, ttl)
        outcome = QueryOutcome(query, "ok", response.articles, credits=cost)
        return await self._record(
            outcome,
            response.params,
            search_id,
            started=started,
            http_status=response.http_status,
        )
