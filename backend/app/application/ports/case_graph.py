"""Puerto de los puntos del muro de un caso sobre el globo (Fase 9.6).

``CaseGraphRepositoryPort`` lo implementa ``PostgresCaseGraphRepository``
(``app/adapters/persistence/case_graph_repository.py``); las pruebas usan una
versión en memoria. Da los puntos que necesita el muro: el de cada lugar ya
ubicado y la ubicación principal de cada nota del caso. Las entidades y los
vínculos salen de sus propios puertos (9.4 y 9.5).

No hace: no decide posiciones (eso es ``app.domain.case_graph``) ni permisos.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.case_graph import GeoPoint


@dataclass(frozen=True, slots=True)
class NoteSource:
    """Una nota del caso para la constelación.

    Attributes:
        article_id: Nota.
        title: Título.
        url: Liga a la nota original.
        published_at: Fecha.
        point: Su ubicación principal, si se ubicó.
    """

    article_id: int
    title: str
    url: str
    published_at: datetime | None
    point: GeoPoint | None


@dataclass(frozen=True, slots=True)
class GraphPoints:
    """Los puntos del catálogo que usa el muro de un caso.

    Attributes:
        entity_points: Punto de cada lugar ya ubicado (región o colonia).
        notes: Las notas del caso con su ubicación principal.
    """

    entity_points: dict[int, GeoPoint]
    notes: tuple[NoteSource, ...]


@dataclass(frozen=True, slots=True)
class CaseOnMap:
    """Un caso de la persona, para ponerlo en el globo («Mis casos», D9).

    Attributes:
        case_id: Caso.
        name: Nombre.
        sensitivity: Nivel de reserva (código).
        article_count: Notas del caso.
        confirmed_count: Entidades confirmadas.
        point: Centro de sus notas ubicadas, o ``None`` si ninguna lo está.
    """

    case_id: UUID
    name: str
    sensitivity: str
    article_count: int
    confirmed_count: int
    point: GeoPoint | None


class CaseGraphRepositoryPort(Protocol):
    """Puntos del catálogo para dibujar casos sobre el globo."""

    async def points(self, case_id: UUID, entity_ids: list[int]) -> GraphPoints:
        """Los puntos de los lugares pedidos y de las notas del caso.

        Args:
            case_id: Caso.
            entity_ids: Entidades que se van a dibujar.

        Returns:
            El punto de cada lugar ubicado y las notas con su ubicación.
        """
        ...

    async def cases_on_map(self, user_id: str) -> list[CaseOnMap]:
        """Los casos abiertos de los que la persona es miembro, con su centro.

        Args:
            user_id: Quién pregunta.

        Returns:
            Sus casos abiertos, sin orden particular.
        """
        ...
