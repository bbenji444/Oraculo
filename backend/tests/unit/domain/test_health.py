"""Reglas del estado de salud del sistema."""

from app.domain.health import ComponentHealth, ComponentStatus, SystemHealth, SystemStatus


def test_sistema_sano_cuando_todos_los_componentes_estan_ok() -> None:
    health = SystemHealth(
        components=(ComponentHealth.ok("database"), ComponentHealth.ok("redis")),
    )

    assert health.status is SystemStatus.OK
    assert health.is_healthy


def test_un_componente_con_error_degrada_el_sistema() -> None:
    health = SystemHealth(
        components=(ComponentHealth.ok("database"), ComponentHealth.error("redis", "caído")),
    )

    assert health.status is SystemStatus.DEGRADED
    assert not health.is_healthy


def test_sin_componentes_no_hay_evidencia_y_se_considera_degradado() -> None:
    assert SystemHealth(components=()).status is SystemStatus.DEGRADED


def test_ok_guarda_info_como_copia_independiente() -> None:
    info = {"version": "16"}
    component = ComponentHealth.ok("database", info=info)
    info["version"] = "otra"

    assert component.status is ComponentStatus.OK
    assert component.info == {"version": "16"}
    assert component.detail is None


def test_error_guarda_el_detalle() -> None:
    component = ComponentHealth.error("worker", "Ningún worker respondió.")

    assert component.status is ComponentStatus.ERROR
    assert component.detail == "Ningún worker respondió."


def test_with_latency_devuelve_copia_sin_modificar_el_original() -> None:
    original = ComponentHealth.ok("redis", info={"version": "8"})

    measured = original.with_latency(12.5)

    assert measured.latency_ms == 12.5
    assert measured.info == {"version": "8"}
    assert original.latency_ms is None
