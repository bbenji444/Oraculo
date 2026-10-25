"""Puerto de historias: leer notas por fecha y guardar su ``story_id`` (F12.1c).

``GroupStories`` (después de cada búsqueda) y ``RegroupAllStories``
(``make agrupar-historias``) deciden con ``assign_stories`` del dominio; la
implementación (``adapters/persistence``) solo lee y escribe.

No hace: no decide qué notas van juntas.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from app.domain.stories import StoryNote


@dataclass(frozen=True, slots=True)
class StoryWindow:
    """Notas por agrupar y sus vecinas en fecha.

    Attributes:
        targets: Las notas pedidas (con fecha; las que no tienen se omiten).
        neighbors: Notas de la ventana de fechas alrededor, sin las pedidas.
    """

    targets: tuple[StoryNote, ...]
    neighbors: tuple[StoryNote, ...]


class StoryStorePort(Protocol):
    """Lectura de notas para agrupar y guardado de sus historias."""

    async def window(self, article_ids: Sequence[int], span: timedelta) -> StoryWindow:
        """Las notas pedidas y las publicadas a ±``span`` de ellas.

        Args:
            article_ids: Notas por agrupar.
            span: Margen de fechas alrededor de las pedidas.

        Returns:
            Las pedidas y sus vecinas.
        """
        ...

    async def fetch_all(self, after_id: int, limit: int) -> Sequence[StoryNote]:
        """Notas con fecha y id mayor que ``after_id``, en orden de id.

        Args:
            after_id: Último id del lote anterior (0 al empezar).
            limit: Tamaño del lote.

        Returns:
            Las notas; vacío cuando ya no hay más.
        """
        ...

    async def save(self, stories: Mapping[int, int | None]) -> None:
        """Guarda la historia de cada nota en una transacción.

        Args:
            stories: ``article_id → story_id`` (``None`` deja la nota sola).
        """
        ...
