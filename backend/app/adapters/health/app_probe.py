"""Revisor de salud de la propia API.

Si este revisor se ejecuta, la API está viva y atendiendo peticiones; reporta
su versión y entorno para saber qué está corriendo.

No hace: no revisa dependencias externas (cada una tiene su revisor).
"""

from app.domain.health import ComponentHealth


class AppHealthProbe:
    """Reporta que la API responde, con su versión y entorno."""

    name = "api"

    def __init__(self, version: str, environment: str) -> None:
        """Guarda los datos a reportar.

        Args:
            version: Versión de la aplicación.
            environment: Entorno de ejecución (``development``...).
        """
        self._version = version
        self._environment = environment

    async def check(self) -> ComponentHealth:
        """Devuelve siempre un resultado sano con versión y entorno.

        Returns:
            Estado ``OK`` de la API.
        """
        return ComponentHealth.ok(
            self.name, info={"version": self._version, "environment": self._environment}
        )
