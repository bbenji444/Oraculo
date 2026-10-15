"""Caso de uso CheckSystemHealth con revisores falsos (sin servicios reales)."""

import asyncio

import pytest

from app.application.use_cases.check_health import CheckSystemHealth
from app.domain.health import ComponentHealth, ComponentStatus, SystemStatus


class FakeProbe:
    """Revisor configurable: devuelve un resultado fijo, tarda o falla."""

    def __init__(
        self,
        name: str,
        result: ComponentHealth | None = None,
        *,
        delay_seconds: float = 0.0,
        raises: Exception | None = None,
    ) -> None:
        self.name = name
        self._result = result or ComponentHealth.ok(name)
        self._delay_seconds = delay_seconds
        self._raises = raises

    async def check(self) -> ComponentHealth:
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        if self._raises:
            raise self._raises
        return self._result


@pytest.mark.anyio
async def test_todos_ok_da_sistema_ok_y_conserva_el_orden() -> None:
    use_case = CheckSystemHealth([FakeProbe("api"), FakeProbe("database")], timeout_seconds=1)

    health = await use_case.execute()

    assert health.status is SystemStatus.OK
    assert [c.name for c in health.components] == ["api", "database"]
    assert all(c.latency_ms is not None for c in health.components)


@pytest.mark.anyio
async def test_un_error_reportado_degrada_el_sistema() -> None:
    failing = FakeProbe("redis", ComponentHealth.error("redis", "No se pudo conectar."))
    use_case = CheckSystemHealth([FakeProbe("api"), failing], timeout_seconds=1)

    health = await use_case.execute()

    assert health.status is SystemStatus.DEGRADED
    assert health.components[1].detail == "No se pudo conectar."


@pytest.mark.anyio
async def test_una_excepcion_inesperada_se_convierte_en_error_sin_tumbar_la_revision() -> None:
    use_case = CheckSystemHealth(
        [FakeProbe("database", raises=RuntimeError("boom")), FakeProbe("api")],
        timeout_seconds=1,
    )

    health = await use_case.execute()

    database, api = health.components
    assert database.status is ComponentStatus.ERROR
    assert database.detail == "Error inesperado: RuntimeError"
    assert api.status is ComponentStatus.OK


@pytest.mark.anyio
async def test_un_componente_lento_se_marca_con_error_por_tiempo() -> None:
    use_case = CheckSystemHealth([FakeProbe("worker", delay_seconds=1)], timeout_seconds=0.05)

    health = await use_case.execute()

    (worker,) = health.components
    assert worker.status is ComponentStatus.ERROR
    assert worker.detail == "No respondió en 0.05 segundos."


@pytest.mark.anyio
async def test_los_componentes_se_revisan_en_paralelo() -> None:
    probes = [FakeProbe(f"p{i}", delay_seconds=0.1) for i in range(5)]
    use_case = CheckSystemHealth(probes, timeout_seconds=1)

    loop = asyncio.get_running_loop()
    started = loop.time()
    await use_case.execute()
    elapsed = loop.time() - started

    # En serie tardaría 0.5 s; en paralelo, poco más de 0.1 s.
    assert elapsed < 0.3


@pytest.mark.parametrize("timeout", [0, -1])
def test_timeout_no_positivo_es_invalido(timeout: float) -> None:
    with pytest.raises(ValueError, match="mayor que cero"):
        CheckSystemHealth([], timeout_seconds=timeout)
