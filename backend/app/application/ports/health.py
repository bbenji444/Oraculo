"""Puerto para revisar la salud de un componente externo.

Cada componente que el sistema necesita (base de datos, Redis, worker...)
tiene un adaptador que implementa este puerto. El caso de uso
``CheckSystemHealth`` los recibe como lista, sin saber cómo funcionan.

No hace: no define qué componentes existen; eso se decide al armar la
aplicación (``app.main``).
"""

from typing import Protocol

from app.domain.health import ComponentHealth


class HealthProbePort(Protocol):
    """Revisa si un componente responde como se espera.

    Attributes:
        name: Nombre estable del componente, igual al que aparece en la
            respuesta de ``/health``.
    """

    name: str

    async def check(self) -> ComponentHealth:
        """Revisa el componente.

        Las implementaciones deben devolver ``ComponentHealth.error`` cuando
        detecten un problema conocido. Si lanzan una excepción inesperada,
        el caso de uso la convierte en error; no tumba la revisión completa.

        Returns:
            El estado del componente.
        """
        ...
