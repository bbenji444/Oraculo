"""Ejecutar las consultas de una búsqueda (paso 2 del pipeline, especificación §9).

Recibe las consultas ya planeadas (``build_queries``) y, para cada una:

1. **Presupuesto.** Si la búsqueda planea más consultas de pago que
   ``MAX_QUERIES_PER_SEARCH`` o más gratuitas que ``MAX_FREE_QUERIES_PER_SEARCH``
   (ADR-0109), se rechaza completa **antes** de enviar nada.
2. **Proveedor disponible.** Si no está configurado (SearchApi sin llave) o
   está apagado (GDELT, ADR-0012; Google News RSS si se apaga, ADR-0021), la
   consulta se registra como ``skipped`` con el motivo.
3. **Caché.** Una consulta idéntica reciente se responde desde la caché: no
   se envía ni cuesta créditos. El índice local no usa caché: cambia cada
   15 minutos y consultarlo es gratis (ADR-0013).
4. **Tope mensual.** Si una consulta de pago haría pasar el tope de
   créditos del mes, se salta.
5. **Envío y registro.** Cada consulta queda en ``provider_queries``.

Que falle un proveedor no tumba la búsqueda (§8): el resultado es
``partial`` y dice qué falló.

Excepción (revisión del 18/11/2026, ADR-0115): si Google web no pudo buscar
porque la cuenta de SearchApi no tiene saldo o rechazó la llave, la consulta
lleva un aviso (``notice``: «Google web no pudo buscar: sin créditos de
SearchApi») y, si otra fuente sí respondió, cuenta como respondida sin notas:
la búsqueda no queda «parcial» por eso, porque no hay nada que reintentar. El
registro de ``provider_queries`` sí guarda el error real. Si Google web era
lo único, la búsqueda falla como siempre, con el aviso. El aviso se entrega a
``on_notice`` para que el worker lo deje en ``searches.progress.notice``.

No hace: no deduplica, no lee las notas ni las guarda (pasos 3 en adelante,
F4).
"""

import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
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
from app.domain.budget import (
    MonthlyCredits,
    QueryCaps,
    account_label,
    account_providers,
    check_query_count,
    credit_account,
    month_start,
)
from app.domain.errors import ProviderAuthError, ProviderError, ProviderNoCreditsError
from app.domain.queries import PlannedQuery, Provider
from app.domain.query_dialects import DIALECTS

_MS_PER_SECOND = 1000
_SECONDS_PER_HOUR = 3600
# Avisos cuando la cuenta de SearchApi no deja buscar (ADR-0115). El texto es
# el contrato con la pantalla (``searches.progress.notice``).
NO_CREDITS_NOTICE = "{source} no pudo buscar: sin créditos de SearchApi"
REJECTED_KEY_NOTICE = "{source} no pudo buscar: SearchApi rechazó la llave"
# Solo Google web: el motor de Google News de SearchApi sigue como estaba
# (error y búsqueda parcial) para no cambiar nada fuera de esta revisión.
ACCOUNT_NOTICE_PROVIDERS = frozenset({Provider.SEARCHAPI_WEB})
_NOTICE_SEPARATOR = "; "


def account_notice(provider: Provider, error: ProviderError) -> str | None:
    """El aviso para el analista si el error es de la cuenta de SearchApi.

    Args:
        provider: Proveedor de la consulta.
        error: Lo que respondió el adaptador.

    Returns:
        «Google web no pudo buscar: ...» si Google web se quedó sin saldo o
        su llave fue rechazada; ``None`` para cualquier otro error.

    Example:
        >>> account_notice(Provider.SEARCHAPI_WEB, ProviderNoCreditsError("x", provider="w"))
        'Google web no pudo buscar: sin créditos de SearchApi'
    """
    if provider not in ACCOUNT_NOTICE_PROVIDERS:
        return None
    source = DIALECTS[provider].label
    if isinstance(error, ProviderNoCreditsError):
        return NO_CREDITS_NOTICE.format(source=source)
    if isinstance(error, ProviderAuthError):
        return REJECTED_KEY_NOTICE.format(source=source)
    return None


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
        notice: Aviso para el analista si la cuenta de SearchApi no dejó
            buscar (``account_notice``). Con aviso y otra fuente que sí
            respondió, ``status`` es ``ok`` sin notas.
    """

    query: PlannedQuery
    status: QueryStatus
    articles: tuple[RawArticle, ...] = ()
    from_cache: bool = False
    credits: int = 0
    message: str | None = None
    notice: str | None = None


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
    def notice(self) -> str | None:
        """Los avisos de las consultas, sin repetir, o ``None`` si no hubo."""
        found = dict.fromkeys(o.notice for o in self.outcomes if o.notice)
        return _NOTICE_SEPARATOR.join(found) or None

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
        query_caps: Topes de consultas por búsqueda (de pago y gratuitas).
        cache_ttl_hours: ``QUERY_CACHE_TTL_HOURS`` (0 = sin caché).
        monthly_credit_limits: Tope mensual de créditos por proveedor de pago
            (``SEARCHAPI_MONTHLY_CREDIT_LIMIT``). Vale para toda su cuenta:
            el de ``searchapi`` cubre también Google web (ADR-0115).
    """

    query_caps: QueryCaps
    cache_ttl_hours: float
    monthly_credit_limits: Mapping[Provider, int]


class ExecuteQueries:
    """Envía las consultas planeadas con presupuesto, caché y registro."""

    def __init__(  # noqa: PLR0913 — cuatro piezas más el reloj y el aviso, estos dos por nombre (*)
        self,
        providers: Mapping[Provider, NewsProviderPort],
        cache: QueryCachePort,
        log: ProviderQueryLogPort,
        limits: ExecutionLimits,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        on_notice: Callable[[UUID, str], None] | None = None,
    ) -> None:
        """Recibe los adaptadores y los límites.

        Args:
            providers: Adaptador de cada proveedor.
            cache: Caché de consultas.
            log: Registro de peticiones.
            limits: Límites de la configuración.
            now: Reloj (las pruebas lo fijan).
            on_notice: Recibe ``(search_id, aviso)`` cuando la cuenta de
                SearchApi no dejó buscar; el worker lo guarda en
                ``searches.progress.notice`` (``NoticedSearchStore``).
        """
        self._providers = providers
        self._cache = cache
        self._log = log
        self._limits = limits
        self._now = now
        self._on_notice = on_notice

    async def execute(
        self, queries: Sequence[PlannedQuery], search_id: UUID | None = None
    ) -> ExecutionResult:
        """Ejecuta las consultas.

        Args:
            queries: Consultas planeadas (``build_queries``).
            search_id: Búsqueda a la que pertenecen (para el registro).

        Returns:
            Qué pasó con cada consulta y el estado global. Una consulta con
            aviso de cuenta (``notice``) cuenta como respondida si otra fuente
            sí respondió.

        Raises:
            QueryBudgetExceededError: Si son más de las permitidas; en ese
                caso no se envía nada.
        """
        check_query_count([q.provider for q in queries], self._limits.query_caps)
        since = month_start(self._now(), MEXICO_CITY)
        # Un presupuesto por cuenta de créditos, no por proveedor: Google News y
        # Google web gastan la misma cuenta de SearchApi y comparten el tope
        # (ADR-0115), así que las reservas de uno cuentan para el otro.
        budgets: dict[str, MonthlyCredits] = {}
        for provider, limit in self._limits.monthly_credit_limits.items():
            account = credit_account(provider)
            if account in budgets:
                continue
            sharing = [p.value for p in account_providers(provider)]
            used = await self._log.credits_used_since(sharing, since)
            budgets[account] = MonthlyCredits(used=used, limit=limit)
        outcomes = tuple(
            await asyncio.gather(*(self._run_one(query, budgets, search_id) for query in queries))
        )
        if any(o.status == "ok" and o.notice is None for o in outcomes):
            # Otra fuente sí respondió: lo de la cuenta de SearchApi es un aviso,
            # no una falla (no hay qué reintentar). El registro ya guardó el error.
            outcomes = tuple(
                replace(o, status="ok", message=None) if o.notice else o for o in outcomes
            )
        result = ExecutionResult(outcomes)
        notice = result.notice
        if notice is not None and search_id is not None and self._on_notice is not None:
            self._on_notice(search_id, notice)
        return result

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
        budgets: Mapping[str, MonthlyCredits],
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
        monthly = budgets.get(credit_account(query.provider))
        if cost and monthly is not None and not monthly.try_reserve(cost):
            outcome = QueryOutcome(
                query,
                "skipped",
                message=(
                    f"Se alcanzó el tope mensual de créditos de {account_label(query.provider)} "
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
            outcome = QueryOutcome(
                query,
                "error",
                message=error.message,
                notice=account_notice(query.provider, error),
            )
            return await self._record(
                outcome, params, search_id, started=started, http_status=error.http_status
            )
        ttl = int(self._limits.cache_ttl_hours * _SECONDS_PER_HOUR)
        if cacheable:
            await self._cache.set(key, response.articles, ttl)
        # Con páginas, la reserva fue el máximo: se devuelve lo que no se gastó.
        spent = cost if response.credits_used is None else response.credits_used
        if monthly is not None and spent < cost:
            monthly.release(cost - spent)
        outcome = QueryOutcome(query, "ok", response.articles, credits=spent)
        return await self._record(
            outcome,
            response.params,
            search_id,
            started=started,
            http_status=response.http_status,
        )
