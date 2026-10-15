"""Modelo del estado de salud del sistema.

Define cómo se representa la salud de cada componente (API, base de datos,
Redis, worker) y la regla para decidir si el sistema completo está sano.
Lo usan el caso de uso ``CheckSystemHealth`` y el endpoint ``/health``.

No hace: no sabe cómo revisar cada componente (eso lo hacen los adaptadores
que implementan ``HealthProbePort``) ni cómo se serializa a JSON.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class ComponentStatus(StrEnum):
    """Estado de un componente individual."""

    OK = "ok"
    ERROR = "error"


class SystemStatus(StrEnum):
    """Estado agregado del sistema completo."""

    OK = "ok"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    """Resultado de revisar un componente.

    Attributes:
        name: Nombre estable del componente (``database``, ``redis``...).
        status: Si el componente respondió como se esperaba.
        detail: Explicación en español para el analista o el operador,
            sobre todo cuando hay error. ``None`` si no hay nada que decir.
        latency_ms: Cuánto tardó la revisión, en milisegundos.
        info: Datos adicionales útiles para diagnosticar (versiones,
            número de workers...). Siempre texto para que sea fácil de mostrar.
    """

    name: str
    status: ComponentStatus
    detail: str | None = None
    latency_ms: float | None = None
    info: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def ok(cls, name: str, *, info: Mapping[str, str] | None = None) -> "ComponentHealth":
        """Crea un resultado sano.

        Args:
            name: Nombre del componente.
            info: Datos adicionales de diagnóstico.

        Returns:
            Un ``ComponentHealth`` con estado ``OK``.
        """
        return cls(name=name, status=ComponentStatus.OK, info=dict(info or {}))

    @classmethod
    def error(cls, name: str, detail: str) -> "ComponentHealth":
        """Crea un resultado con error.

        Args:
            name: Nombre del componente.
            detail: Qué falló, en español claro.

        Returns:
            Un ``ComponentHealth`` con estado ``ERROR``.
        """
        return cls(name=name, status=ComponentStatus.ERROR, detail=detail)

    def with_latency(self, latency_ms: float) -> "ComponentHealth":
        """Devuelve una copia con la latencia medida.

        Args:
            latency_ms: Duración de la revisión en milisegundos.

        Returns:
            Un nuevo ``ComponentHealth`` igual al actual pero con latencia.
        """
        return ComponentHealth(
            name=self.name,
            status=self.status,
            detail=self.detail,
            latency_ms=latency_ms,
            info=self.info,
        )


@dataclass(frozen=True, slots=True)
class SystemHealth:
    """Salud de todos los componentes revisados en un momento dado.

    Attributes:
        components: Resultado de cada componente, en el orden en que se
            revisaron.
    """

    components: tuple[ComponentHealth, ...]

    @property
    def status(self) -> SystemStatus:
        """Estado agregado: sano solo si **todos** los componentes lo están.

        Un sistema sin componentes revisados se considera degradado: no hay
        evidencia de que funcione.
        """
        if self.components and all(c.status is ComponentStatus.OK for c in self.components):
            return SystemStatus.OK
        return SystemStatus.DEGRADED

    @property
    def is_healthy(self) -> bool:
        """``True`` si el estado agregado es ``OK``."""
        return self.status is SystemStatus.OK
