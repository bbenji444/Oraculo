"""Colas sobre Celery: búsquedas (``search.run``) y entidades de un caso (``entities.extract``).

Usa ``send_task`` con el nombre de la tarea, sin importar su código: la API
no necesita cargar el pipeline para encolarlo. El worker la recibe por
Redis (el broker).

No hace: no espera el resultado (la pantalla consulta ``GET /searches/{id}``
o ``GET /cases/{id}/entities``).
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


# Lectura de una nota de un caso por la IA (Fase 9.4; la registra app.worker.tasks).
ENTITIES_TASK = "entities.extract"


class CeleryEntityQueue:
    """``EntityQueuePort`` sobre Celery: encola la tarea ``entities.extract``."""

    def __init__(self, app: Celery) -> None:
        """Recibe la app de Celery compartida.

        Args:
            app: App de Celery conectada al broker.
        """
        self._app = app

    def enqueue(self, case_id: UUID, article_id: int, requested_by: str) -> None:
        """Ver ``EntityQueuePort.enqueue``."""
        # Texto y no UUID: los mensajes de Celery son JSON.
        self._app.send_task(ENTITIES_TASK, args=[str(case_id), article_id, requested_by])
