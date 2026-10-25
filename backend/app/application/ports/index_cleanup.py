"""Puerto para limpiar duplicados del índice local (F12.1b, ADR-0025).

``CleanIndexDuplicates`` lee las llaves de todas las notas por lotes, decide
con ``plan_index_cleanup`` qué sobra y le pide a este puerto borrar y
recalcular huellas. La implementación vive en ``adapters/persistence``.

No hace: no decide qué sobra.
"""

from collections.abc import Sequence
from typing import Protocol

from app.domain.index_cleanup import IndexKey


class IndexCleanupPort(Protocol):
    """Lectura por lotes, borrado y recálculo de huellas en ``news_index``."""

    async def fetch_keys(self, after_id: int, limit: int) -> Sequence[IndexKey]:
        """Llaves de las notas con id mayor que ``after_id``, en orden.

        Args:
            after_id: Último id del lote anterior (0 al empezar).
            limit: Tamaño del lote.

        Returns:
            Las llaves; vacío cuando ya no hay más.
        """
        ...

    async def delete(self, note_ids: Sequence[int]) -> int:
        """Borra notas del índice en una transacción.

        Args:
            note_ids: Ids a borrar.

        Returns:
            Cuántas se borraron.
        """
        ...

    async def rehash(self, pairs: Sequence[tuple[int, str]]) -> None:
        """Cambia la huella (``url_hash``) de notas, en una transacción.

        Args:
            pairs: ``(id, huella nueva)``.
        """
        ...
