"""Revisor de salud del worker de Celery (ADR-0005).

Envía un ``ping`` de control por el broker y espera la respuesta de al menos
un worker. Si nadie contesta, las búsquedas se encolarían pero nunca se
procesarían, así que se reporta como error.

No hace: no revisa las tareas en ejecución ni el tamaño de la cola.
"""

import asyncio

from celery import Celery
from kombu.exceptions import OperationalError

from app.domain.health import ComponentHealth


class CeleryWorkerHealthProbe:
    """Pregunta por el broker si hay workers vivos."""

    name = "worker"

    def __init__(self, celery_app: Celery, reply_timeout_seconds: float) -> None:
        """Guarda la app de Celery y el tiempo de espera de respuestas.

        Args:
            celery_app: App de Celery conectada al mismo broker que el worker.
            reply_timeout_seconds: Cuánto esperar respuestas de los workers.
                Debe ser menor que el límite del caso de uso para que el
                mensaje de error sea el de este revisor.
        """
        self._celery_app = celery_app
        self._reply_timeout_seconds = reply_timeout_seconds

    async def check(self) -> ComponentHealth:
        """Hace ping a los workers.

        ``control.ping`` es bloqueante, así que corre en un hilo aparte para
        no frenar el event loop de la API.

        Returns:
            ``OK`` con el número de workers que respondieron, o ``ERROR`` si
            ninguno respondió o el broker no está disponible.
        """
        try:
            replies = await asyncio.to_thread(
                self._celery_app.control.ping, timeout=self._reply_timeout_seconds
            )
        except (OperationalError, OSError) as exc:
            return ComponentHealth.error(
                self.name, f"No se pudo hablar con el broker ({type(exc).__name__})."
            )
        if not replies:
            return ComponentHealth.error(
                self.name, "Ningún worker respondió. ¿Está corriendo `make up`?"
            )
        return ComponentHealth.ok(self.name, info={"workers": str(len(replies))})
