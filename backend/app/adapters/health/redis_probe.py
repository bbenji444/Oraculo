"""Revisor de salud de Redis (cola de Celery y caché, ADR-0005).

No hace: no revisa si hay tareas en cola ni el estado de la caché.
"""

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.domain.health import ComponentHealth


class RedisHealthProbe:
    """Hace PING a Redis y reporta su versión."""

    name = "redis"

    def __init__(self, client: Redis) -> None:
        """Guarda el cliente de Redis.

        Args:
            client: Cliente asíncrono de Redis ya configurado.
        """
        self._client = client

    async def check(self) -> ComponentHealth:
        """Envía PING y lee la versión del servidor.

        Returns:
            ``OK`` con la versión si responde; ``ERROR`` si no hay conexión.
        """
        try:
            await self._client.ping()
            server_info = await self._client.info(section="server")
        except (RedisError, OSError) as exc:
            return ComponentHealth.error(
                self.name, f"No se pudo conectar a Redis ({type(exc).__name__})."
            )
        return ComponentHealth.ok(self.name, info={"version": str(server_info["redis_version"])})
