"""Aviso para el analista en ``searches.progress.notice`` (ADR-0115).

Revisión del 18/11/2026: si la cuenta de SearchApi se queda sin saldo (o
rechaza la llave) a media búsqueda, Google web no trae nada pero la búsqueda
sigue con las demás fuentes. Para que el analista sepa por qué no salieron
Facebook ni X, el worker deja en el avance de la búsqueda
``notice = "Google web no pudo buscar: sin créditos de SearchApi"``.

``RunSearch`` reemplaza el avance completo en cada etapa (``set_progress`` y
``finish``), así que el aviso se pone en **cada** escritura: este decorador
envuelve el ``SearchStorePort`` del worker y agrega el aviso que dejó
``ExecuteQueries`` (``on_notice``). Así ``RunSearch`` no cambia.

Lo usa ``app/worker/search_jobs.py``. No hace: no decide cuándo hay aviso
(eso es ``ExecuteQueries``) ni guarda nada por su cuenta.
"""

from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from app.application.audit import Actor
from app.application.ports.search_store import (
    NewSearch,
    ProcessingErrorRecord,
    SearchClosing,
    SearchStorePort,
    StoredSearch,
)

# Clave del aviso dentro de ``searches.progress``: contrato con la pantalla
# (``progress.notice``, texto opcional).
NOTICE_KEY = "notice"


class SearchNotices:
    """Los avisos de las búsquedas que corren en este proceso, en memoria."""

    def __init__(self) -> None:
        """Empieza sin avisos."""
        self._notices: dict[UUID, str] = {}

    def put(self, search_id: UUID, notice: str) -> None:
        """Guarda el aviso de una búsqueda (``ExecuteQueries.on_notice``).

        Args:
            search_id: Búsqueda.
            notice: Texto para el analista.
        """
        self._notices[search_id] = notice

    def stamp(self, search_id: UUID, progress: Mapping[str, object]) -> Mapping[str, object]:
        """El avance con el aviso de la búsqueda, si tiene.

        Args:
            search_id: Búsqueda.
            progress: Avance que escribe ``RunSearch``.

        Returns:
            El mismo avance, o una copia con ``notice`` si hay aviso.
        """
        notice = self._notices.get(search_id)
        return progress if notice is None else {**progress, NOTICE_KEY: notice}

    def forget(self, search_id: UUID) -> None:
        """Olvida el aviso de una búsqueda ya cerrada.

        Args:
            search_id: Búsqueda.
        """
        self._notices.pop(search_id, None)


class NoticedSearchStore:
    """``SearchStorePort`` que agrega el aviso de la búsqueda a cada avance."""

    def __init__(self, inner: SearchStorePort, notices: SearchNotices) -> None:
        """Recibe el almacén real y los avisos.

        Args:
            inner: Almacén de búsquedas de siempre.
            notices: Avisos que deja ``ExecuteQueries``.
        """
        self._inner = inner
        self._notices = notices

    async def create(self, search: NewSearch) -> UUID:
        """Ver ``SearchStorePort.create``."""
        return await self._inner.create(search)

    async def load(self, search_id: UUID) -> StoredSearch | None:
        """Ver ``SearchStorePort.load``."""
        return await self._inner.load(search_id)

    async def start(self, search_id: UUID) -> None:
        """Ver ``SearchStorePort.start``."""
        await self._inner.start(search_id)

    async def set_progress(self, search_id: UUID, progress: Mapping[str, object]) -> None:
        """Ver ``SearchStorePort.set_progress``; agrega el aviso si hay."""
        await self._inner.set_progress(search_id, self._notices.stamp(search_id, progress))

    async def record_error(self, error: ProcessingErrorRecord) -> None:
        """Ver ``SearchStorePort.record_error``."""
        await self._inner.record_error(error)

    async def finish(self, search_id: UUID, closing: SearchClosing, actor: Actor) -> None:
        """Ver ``SearchStorePort.finish``; el avance final lleva el aviso si hay."""
        stamped = replace(closing, progress=self._notices.stamp(search_id, closing.progress))
        try:
            await self._inner.finish(search_id, stamped, actor)
        finally:
            self._notices.forget(search_id)
