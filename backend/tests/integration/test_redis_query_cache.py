"""Caché de consultas contra el Redis de pruebas (REDIS_TEST_URL)."""

from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis

from app.adapters.cache.redis_query_cache import KEY_PREFIX, RedisQueryCache
from app.application.ports.query_cache import cache_key
from app.domain.articles import RawArticle
from app.domain.queries import Provider

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

KEY = cache_key("searchapi", "hackeo Peñón", {"q": "hackeo Peñón", "gl": "mx"})


def article() -> RawArticle:
    return RawArticle.create(
        provider=Provider.SEARCHAPI,
        provider_rank=1,
        url="https://www.milenio.com/policia/peñon",
        title="Hackeo en Peñón de los Baños",
        source_name="Milenio",
        published_at=datetime(2026, 10, 15, 14, 30, tzinfo=UTC),
        snippet="Fragmento",
        raw={"position": 1},
    )


async def test_guarda_y_recupera_con_enie_y_tiempo_de_vida(test_redis: Redis) -> None:
    await test_redis.delete(KEY_PREFIX + KEY)
    cache = RedisQueryCache(test_redis)

    await cache.set(KEY, (article(),), ttl_seconds=60)
    restored = await cache.get(KEY)

    assert restored == (article(),)
    assert 0 < await test_redis.ttl(KEY_PREFIX + KEY) <= 60
    await test_redis.delete(KEY_PREFIX + KEY)


async def test_sin_entrada_devuelve_none_y_ttl_cero_no_guarda(test_redis: Redis) -> None:
    await test_redis.delete(KEY_PREFIX + KEY)
    cache = RedisQueryCache(test_redis)

    await cache.set(KEY, (article(),), ttl_seconds=0)

    assert await cache.get(KEY) is None


async def test_si_redis_no_responde_la_busqueda_sigue_sin_cache() -> None:
    # Puerto sin servidor: leer devuelve "no hay" y guardar se omite.
    broken = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    cache = RedisQueryCache(broken)

    assert await cache.get(KEY) is None
    await cache.set(KEY, (article(),), ttl_seconds=60)
    await broken.aclose()


def test_la_huella_no_depende_del_orden_de_los_parametros() -> None:
    a = cache_key("gdelt", "x", {"a": "1", "b": "2"})
    b = cache_key("gdelt", "x", {"b": "2", "a": "1"})

    assert a == b
    assert cache_key("gdelt", "y", {"a": "1", "b": "2"}) != a
