"""``SearchQueuePort`` sobre Celery: encola la tarea ``search.run``.

Usa ``send_task`` con el nombre de la tarea, sin importar su código: la API
no necesita cargar el pipeline para encolarlo. El worker la recibe por
Redis (el broker).

No hace: no espera el resultado (la pantalla consulta ``GET /searches/{id}``).
"""

from uuid import UUID

from celery import Celery

# Nombre estable de la tarea (lo registra app.worker.tasks).
SEARCH_TASK = "search.run"


class CelerySearchQueue:
    """Encola búsquedas en Celery."""

    def __init__(self, app: Celery) -> None:
        """Recibe la app de Celery compartida.

        Args:
            app: App de Celery conectada al broker.
        """
        self._app = app

    def enqueue(self, search_id: UUID) -> None:
        """Ver ``SearchQueuePort.enqueue``."""
        # Texto y no UUID: los mensajes de Celery son JSON.
        self._app.send_task(SEARCH_TASK, args=[str(search_id)])
