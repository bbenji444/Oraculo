"""Esquema de respuesta de ``GET /api/v1/health``.

Traduce el modelo de dominio ``SystemHealth`` al JSON público de la API.
No hace: no decide el estado; solo lo representa.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.health import ComponentHealth, SystemHealth


class ComponentHealthOut(BaseModel):
    """Estado de un componente en la respuesta JSON."""

    name: str = Field(description="Componente revisado: api, database, redis o worker.")
    status: Literal["ok", "error"]
    detail: str | None = Field(default=None, description="Explicación del error, en español.")
    latency_ms: float | None = Field(default=None, description="Duración de la revisión.")
    info: dict[str, str] = Field(default_factory=dict, description="Versiones y otros datos.")

    @classmethod
    def from_domain(cls, component: ComponentHealth) -> "ComponentHealthOut":
        """Convierte un ``ComponentHealth`` del dominio.

        Args:
            component: Resultado del dominio.

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            name=component.name,
            status=component.status.value,
            detail=component.detail,
            latency_ms=component.latency_ms,
            info=dict(component.info),
        )


class HealthOut(BaseModel):
    """Respuesta completa de ``/health``."""

    status: Literal["ok", "degraded"] = Field(
        description="`ok` si todos los componentes están bien; `degraded` si alguno falla."
    )
    components: list[ComponentHealthOut]
    auth_mode: Literal["dev", "keys"] = Field(
        description=(
            "`keys`: la API pide sesión o llave. `dev`: entra cualquiera como superusuario; "
            "solo para la PC de desarrollo, nunca detrás del gateway de Oráculo (ADR-0119)."
        )
    )

    @classmethod
    def from_domain(cls, health: SystemHealth, auth_mode: Literal["dev", "keys"]) -> "HealthOut":
        """Convierte un ``SystemHealth`` del dominio.

        Args:
            health: Estado del sistema.
            auth_mode: Si la API pide llave (``AUTH_MODE``).

        Returns:
            El esquema listo para serializar.
        """
        return cls(
            status=health.status.value,
            components=[ComponentHealthOut.from_domain(c) for c in health.components],
            auth_mode=auth_mode,
        )
