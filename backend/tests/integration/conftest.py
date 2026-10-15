"""Recursos reales para pruebas de integración.

Usan siempre la base ``POSTGRES_TEST_DB`` y el Redis ``REDIS_TEST_URL``,
nunca los de desarrollo (CLAUDE.md §7). Requieren que los servicios estén
arriba (``make up`` o, al menos, PostgreSQL y Redis).
"""

from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def test_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(settings.database_url(test=True))
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_redis(settings: Settings) -> AsyncIterator[Redis]:
    client = Redis.from_url(settings.redis_test_url)
    yield client
    await client.aclose()
