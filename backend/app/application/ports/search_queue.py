"""Puerto de la cola que manda una búsqueda al worker (§9).

La implementación (``app/adapters/queue/celery_queue.py``) encola la tarea
``search.run`` de Celery; las pruebas usan una cola en memoria.

No hace: no corre la búsqueda ni espera a que termine.
"""

from typing import Protocol
from uuid import UUID


class SearchQueuePort(Protocol):
    """Manda una búsqueda guardada a que la corra el worker."""

    def enqueue(self, search_id: UUID) -> None:
        """Encola la búsqueda.

        Args:
            search_id: Búsqueda creada en ``pending``.
        """
        ...
