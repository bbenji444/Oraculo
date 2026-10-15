"""Revisores de salud con clientes falsos (sin servicios reales).

Los caminos con PostgreSQL y Redis reales están en tests/integration.
"""

from typing import Any, cast

import pytest
from kombu.exceptions import OperationalError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.adapters.health.app_probe import AppHealthProbe
from app.adapters.health.celery_probe import CeleryWorkerHealthProbe
from app.adapters.health.redis_probe import RedisHealthProbe
from app.domain.health import ComponentStatus

pytestmark = pytest.mark.anyio


class FakeControl:
    def __init__(self, replies: list[dict[str, Any]] | None, raises: Exception | None) -> None:
        self._replies = replies
        self._raises = raises
        self.timeout: float | None = None

    def ping(self, timeout: float) -> list[dict[str, Any]] | None:
        self.timeout = timeout
        if self._raises:
            raise self._raises
        return self._replies


class FakeCelery:
    def __init__(
        self, replies: list[dict[str, Any]] | None = None, raises: Exception | None = None
    ) -> None:
        self.control = FakeControl(replies, raises)


class FakeRedis:
    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises

    async def ping(self) -> bool:
        if self._raises:
            raise self._raises
        return True

    async def info(self, section: str) -> dict[str, str]:
        return {"redis_version": "8.0.5"}


def as_redis(fake: FakeRedis) -> Redis:
    # El revisor solo usa ping() e info(); el doble implementa esas dos.
    return cast(Redis, fake)


async def test_api_reporta_version_y_entorno() -> None:
    result = await AppHealthProbe(version="0.0.0", environment="development").check()

    assert result.status is ComponentStatus.OK
    assert result.info == {"version": "0.0.0", "environment": "development"}


async def test_worker_ok_cuenta_los_workers_que_respondieron() -> None:
    celery = FakeCelery(replies=[{"celery@a": {"ok": "pong"}}, {"celery@b": {"ok": "pong"}}])

    result = await CeleryWorkerHealthProbe(celery, reply_timeout_seconds=0.5).check()

    assert result.status is ComponentStatus.OK
    assert result.info == {"workers": "2"}
    assert celery.control.timeout == 0.5


@pytest.mark.parametrize("replies", [[], None])
async def test_worker_sin_respuestas_es_error(replies: list[dict[str, Any]] | None) -> None:
    probe = CeleryWorkerHealthProbe(FakeCelery(replies=replies), reply_timeout_seconds=0.1)

    result = await probe.check()

    assert result.status is ComponentStatus.ERROR
    assert result.detail is not None
    assert "Ningún worker respondió" in result.detail


async def test_worker_con_broker_caido_es_error() -> None:
    celery = FakeCelery(raises=OperationalError("Connection refused"))

    result = await CeleryWorkerHealthProbe(celery, reply_timeout_seconds=0.1).check()

    assert result.status is ComponentStatus.ERROR
    assert result.detail == "No se pudo hablar con el broker (OperationalError)."


async def test_redis_ok_reporta_version() -> None:
    result = await RedisHealthProbe(as_redis(FakeRedis())).check()

    assert result.status is ComponentStatus.OK
    assert result.info == {"version": "8.0.5"}


async def test_redis_sin_conexion_es_error() -> None:
    probe = RedisHealthProbe(as_redis(FakeRedis(raises=RedisConnectionError("refused"))))

    result = await probe.check()

    assert result.status is ComponentStatus.ERROR
    assert result.detail == "No se pudo conectar a Redis (ConnectionError)."
