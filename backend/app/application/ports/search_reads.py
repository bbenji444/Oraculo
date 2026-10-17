"""Puerto de lectura de búsquedas para la API (especificación §13).

Separa lo que la pantalla lee (detalle, historial, notas y conteos) de lo
que el pipeline escribe (``search_store``). La implementación está en
``app/adapters/persistence/search_repository.py``.

No hace: no decide nada ni escribe.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.application.pagination import TimeCursor
from app.domain.enrichment import LLMUsage
from app.domain.search import SearchStatus


@dataclass(frozen=True, slots=True)
class ConceptRef:
    """Un concepto tal como se usó en la búsqueda.

    Attributes:
        id: Id del concepto.
        name: Nombre al momento de buscar.
    """

    id: int
    name: str


@dataclass(frozen=True, slots=True)
class SearchDetail:
    """Una búsqueda con su estado, avance y costo.

    Attributes:
        search_id: Id.
        user_id: Quién la pidió.
        status: Estado.
        region_id: Región buscada.
        region_code: Su clave (INEGI o ISO-A3).
        region_name: Su nombre.
        date_from: Primer día.
        date_to: Último día.
        concepts: Conceptos de la búsqueda.
        progress: Etapa actual y conteos (``RunSearch``).
        queries_planned: Consultas planeadas.
        credits_estimated: Créditos estimados.
        credits_used: Créditos gastados.
        llm_usage: Tokens de la IA.
        llm_cost_usd: Costo estimado de la IA.
        results_count: Notas distintas encontradas.
        error_summary: Qué falló, si algo falló.
        created_at: Cuándo se pidió (UTC).
        started_at: Cuándo empezó a correr.
        finished_at: Cuándo terminó.
    """

    search_id: UUID
    user_id: str
    status: SearchStatus
    region_id: int
    region_code: str
    region_name: str
    date_from: date
    date_to: date
    concepts: tuple[ConceptRef, ...]
    progress: Mapping[str, object]
    queries_planned: int
    credits_estimated: int
    credits_used: int
    llm_usage: LLMUsage
    llm_cost_usd: float
    results_count: int
    error_summary: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SearchReaderPort(Protocol):
    """Lecturas de búsquedas para la API."""

    async def search_detail(self, search_id: UUID) -> SearchDetail | None:
        """Una búsqueda.

        Args:
            search_id: Id.

        Returns:
            La búsqueda, o ``None`` si no existe.
        """
        ...

    async def history(
        self, user_id: str, after: TimeCursor | None, limit: int
    ) -> list[SearchDetail]:
        """Búsquedas de una persona, de la más reciente a la más vieja.

        Args:
            user_id: Quién las pidió.
            after: Cursor de la página anterior.
            limit: Cuántas como máximo.

        Returns:
            Las búsquedas de la página.
        """
        ...
