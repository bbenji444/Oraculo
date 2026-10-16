"""Puerto del registro de peticiones a proveedores (tabla ``provider_queries``).

Cada petición queda registrada con su resultado y sus créditos: sirve para
auditar el gasto (CLAUDE.md §8) y para el tope mensual de SearchApi.

No hace: no decide si una consulta se envía (eso es el presupuesto).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.application.audit import Actor

QueryStatus = Literal["ok", "error", "skipped"]


@dataclass(frozen=True, slots=True)
class ProviderQueryRecord:
    """Una petición a un proveedor, lista para registrarse.

    Attributes:
        provider: Proveedor (``searchapi``, ``gdelt``, ``google_news_rss``).
        query_text: Texto exacto enviado.
        params: Parámetros enviados, **sin la llave**.
        status: ``ok``, ``error`` o ``skipped`` (no se envió).
        http_status: Código HTTP, si hubo respuesta.
        results_count: Notas normalizadas que devolvió.
        from_cache: Si se respondió desde la caché (no costó créditos).
        cost_credits: Créditos gastados.
        duration_ms: Duración en milisegundos.
        error_message: Qué falló, en español.
        search_id: Búsqueda a la que pertenece (vacío en el comando de prueba).
    """

    provider: str
    query_text: str
    params: Mapping[str, str]
    status: QueryStatus
    http_status: int | None = None
    results_count: int = 0
    from_cache: bool = False
    cost_credits: int = 0
    duration_ms: int = 0
    error_message: str | None = None
    search_id: UUID | None = field(default=None)


class ProviderQueryLogPort(Protocol):
    """Escritura y consultas del registro de peticiones."""

    async def record(self, entry: ProviderQueryRecord, actor: Actor | None = None) -> int:
        """Guarda una petición; si hay ``actor``, también en la bitácora de auditoría.

        Args:
            entry: La petición.
            actor: Quién la pidió (el comando de prueba); ``None`` dentro de
                una búsqueda, que tiene su propio registro de auditoría.

        Returns:
            El id del registro.
        """
        ...

    async def credits_used_since(self, provider: str, since: datetime) -> int:
        """Créditos gastados en un proveedor desde una fecha.

        Args:
            provider: Proveedor.
            since: Inicio del periodo (por ejemplo, el día 1 del mes, en UTC).

        Returns:
            La suma de ``cost_credits``.
        """
        ...
