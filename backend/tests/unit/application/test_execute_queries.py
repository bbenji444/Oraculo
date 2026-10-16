"""ExecuteQueries con proveedores, caché y registro en memoria (sin red)."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.application.audit import Actor
from app.application.ports.provider_log import ProviderQueryRecord, QueryRun
from app.application.ports.providers import ProviderResponse
from app.application.use_cases.execute_queries import (
    ExecuteQueries,
    ExecutionLimits,
    ExecutionStatus,
)
from app.domain.articles import RawArticle
from app.domain.budget import QueryBudgetExceededError
from app.domain.errors import ProviderUnavailableError
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
WEEK = DateWindow.last_days(7, date(2026, 10, 16))


def planned(provider: Provider, text: str = "hackeo CDMX") -> PlannedQuery:
    return PlannedQuery(provider, text, ("hackeo",), MEXICO, "es", WEEK, 0)


def article(provider: Provider, rank: int = 1) -> RawArticle:
    return RawArticle.create(
        provider=provider,
        provider_rank=rank,
        url=f"https://www.milenio.com/nota-{rank}",
        title=f"Nota {rank}",
    )


class FakeProvider:
    def __init__(
        self,
        provider: Provider,
        *,
        cost: int = 0,
        configured: bool = True,
        error: Exception | None = None,
    ) -> None:
        self._provider = provider
        self.cost = cost
        self.configured = configured
        self.error = error
        self.calls = 0

    @property
    def provider(self) -> Provider:
        return self._provider

    def is_configured(self) -> bool:
        return self.configured

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        return {"q": query.text}

    def estimate_cost(self, query: PlannedQuery) -> int:
        return self.cost

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        self.calls += 1
        if self.error:
            raise self.error
        return ProviderResponse((article(self._provider),), 200, {"q": query.text}, "{}")


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, tuple[RawArticle, ...]] = {}
        self.ttls: list[int] = []

    async def get(self, key: str) -> tuple[RawArticle, ...] | None:
        return self.store.get(key)

    async def set(self, key: str, articles: tuple[RawArticle, ...], ttl_seconds: int) -> None:
        self.ttls.append(ttl_seconds)
        if ttl_seconds > 0:
            self.store[key] = articles


class FakeLog:
    def __init__(self, used: int = 0) -> None:
        self.records: list[ProviderQueryRecord] = []
        self.used = used
        self.asked_since: list[datetime] = []

    async def record(self, entry: ProviderQueryRecord, actor: Actor | None = None) -> int:
        self.records.append(entry)
        return len(self.records)

    async def credits_used_since(self, provider: str, since: datetime) -> int:
        self.asked_since.append(since)
        return self.used

    async def runs_of(self, provider: str, query_text: str) -> list[QueryRun]:
        return []


def use_case(
    *providers: FakeProvider,
    cache: FakeCache | None = None,
    log: FakeLog | None = None,
    max_queries: int = 10,
    monthly_limit: int = 100,
    ttl_hours: float = 6,
) -> tuple[ExecuteQueries, FakeCache, FakeLog]:
    cache = cache or FakeCache()
    log = log or FakeLog()
    limits = ExecutionLimits(max_queries, ttl_hours, {Provider.SEARCHAPI: monthly_limit})
    by_provider = {p.provider: p for p in providers}
    return ExecuteQueries(by_provider, cache, log, limits, now=lambda: NOW), cache, log


async def test_demasiadas_consultas_se_rechazan_sin_enviar_nada() -> None:
    gdelt = FakeProvider(Provider.GDELT)
    execute, _, log = use_case(gdelt, max_queries=2)

    with pytest.raises(QueryBudgetExceededError):
        await execute.execute([planned(Provider.GDELT, str(i)) for i in range(3)])
    assert (gdelt.calls, log.records) == (0, [])


async def test_todo_bien_registra_creditos_y_guarda_en_cache() -> None:
    searchapi = FakeProvider(Provider.SEARCHAPI, cost=1)
    execute, cache, log = use_case(searchapi)
    search_id = uuid4()

    result = await execute.execute([planned(Provider.SEARCHAPI)], search_id)

    assert result.status is ExecutionStatus.COMPLETED
    assert (len(result.articles), result.credits_used) == (1, 1)
    [record] = log.records
    assert (record.status, record.cost_credits, record.from_cache) == ("ok", 1, False)
    assert record.search_id == search_id
    assert cache.ttls == [6 * 3600]
    # El mes se cuenta desde el día 1 en hora de la CDMX.
    assert log.asked_since == [datetime(2026, 10, 1, 6, 0, tzinfo=UTC)]


async def test_consulta_identica_sale_de_la_cache_sin_enviar_ni_cobrar() -> None:
    searchapi = FakeProvider(Provider.SEARCHAPI, cost=1)
    execute, cache, log = use_case(searchapi)
    await execute.execute([planned(Provider.SEARCHAPI)])

    result = await execute.execute([planned(Provider.SEARCHAPI)])

    assert searchapi.calls == 1
    assert result.credits_used == 0
    assert (log.records[-1].from_cache, log.records[-1].cost_credits) == (True, 0)
    assert len(result.articles) == 1
    assert len(cache.store) == 1


async def test_proveedor_desactivado_se_salta_y_la_busqueda_es_parcial() -> None:
    gdelt = FakeProvider(Provider.GDELT, configured=False)
    searchapi = FakeProvider(Provider.SEARCHAPI, cost=1)
    execute, _, log = use_case(gdelt, searchapi)

    result = await execute.execute([planned(Provider.SEARCHAPI), planned(Provider.GDELT)])

    assert result.status is ExecutionStatus.PARTIAL
    assert gdelt.calls == 0
    # Las consultas corren en paralelo: el orden del registro puede variar.
    assert sorted(r.status for r in log.records) == ["ok", "skipped"]
    # El resultado sí conserva el orden recibido.
    assert [o.status for o in result.outcomes] == ["ok", "skipped"]


async def test_proveedor_sin_adaptador_tambien_se_salta() -> None:
    execute, _, _ = use_case(FakeProvider(Provider.SEARCHAPI))

    result = await execute.execute([planned(Provider.GOOGLE_NEWS_RSS)])

    assert result.status is ExecutionStatus.FAILED
    assert result.outcomes[0].message == "google_news_rss no está habilitado."


async def test_un_proveedor_que_falla_no_tumba_la_busqueda_ni_cobra() -> None:
    failing = FakeProvider(
        Provider.SEARCHAPI, cost=1, error=ProviderUnavailableError("caído", provider="searchapi")
    )
    gdelt = FakeProvider(Provider.GDELT)
    execute, cache, log = use_case(failing, gdelt)

    result = await execute.execute([planned(Provider.SEARCHAPI), planned(Provider.GDELT)])

    assert result.status is ExecutionStatus.PARTIAL
    assert result.credits_used == 0
    failed = next(r for r in log.records if r.provider == "searchapi")
    assert (failed.status, failed.error_message, failed.cost_credits) == ("error", "caído", 0)
    assert len(cache.store) == 1


async def test_tope_mensual_salta_lo_que_no_cabe() -> None:
    searchapi = FakeProvider(Provider.SEARCHAPI, cost=1)
    execute, _, log = use_case(searchapi, log=FakeLog(used=99), monthly_limit=100)

    result = await execute.execute(
        [planned(Provider.SEARCHAPI, "uno"), planned(Provider.SEARCHAPI, "dos")]
    )

    assert searchapi.calls == 1
    assert result.credits_used == 1
    skipped = [o for o in result.outcomes if o.status == "skipped"]
    assert len(skipped) == 1
    assert skipped[0].message is not None and "tope mensual" in skipped[0].message
    assert sorted(r.status for r in log.records) == ["ok", "skipped"]


async def test_si_todo_falla_el_estado_es_fallido() -> None:
    failing = FakeProvider(
        Provider.GDELT, error=ProviderUnavailableError("caído", provider="gdelt")
    )
    execute, _, _ = use_case(failing)

    result = await execute.execute([planned(Provider.GDELT)])

    assert result.status is ExecutionStatus.FAILED
    assert result.articles == ()


async def test_sin_cache_configurada_no_guarda() -> None:
    gdelt = FakeProvider(Provider.GDELT)
    execute, cache, _ = use_case(gdelt, ttl_hours=0)

    await execute.execute([planned(Provider.GDELT)])
    await execute.execute([planned(Provider.GDELT)])

    assert gdelt.calls == 2
    assert cache.store == {}


async def test_el_indice_local_nunca_usa_la_cache() -> None:
    # El índice cambia cada 15 minutos (ADR-0013): repetir la búsqueda debe
    # ver las notas nuevas, y consultarlo no cuesta nada.
    local = FakeProvider(Provider.LOCAL_INDEX)
    execute, cache, log = use_case(local)

    await execute.execute([planned(Provider.LOCAL_INDEX)])
    await execute.execute([planned(Provider.LOCAL_INDEX)])

    assert local.calls == 2
    assert (cache.store, cache.ttls) == ({}, [])
    assert [r.from_cache for r in log.records] == [False, False]
