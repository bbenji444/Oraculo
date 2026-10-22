"""Esquemas del muro de un caso y de «Mis casos» en el globo (Fase 9.6).

Cada nodo trae su posición ya calculada en el servidor (§9.5: nunca en cada
cuadro), su estatus legal con etiqueta (siempre visible, §9.10) y si su punto
es propio (un lugar) o una posición visual alrededor del lugar de sus notas.

No hace: no valida reglas de negocio (eso es el dominio).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.v1.schemas.relationships import RelationshipOut
from app.application.ports.case_graph import CaseOnMap
from app.application.use_cases.case_graph import CaseGraph, GraphNode, GraphNote
from app.domain.investigation import (
    ENTITY_TYPE_LABEL,
    LEGAL_STATUS_LABEL,
    SENSITIVITY_LABEL,
    LegalStatus,
    Sensitivity,
)


class PointOut(BaseModel):
    """Un punto sobre el globo."""

    lon: float
    lat: float


class GraphNodeOut(BaseModel):
    """Una entidad confirmada en el muro."""

    id: int
    type: str
    type_label: str
    label: str
    legal_status: LegalStatus | None
    legal_status_label: str | None
    mention_count: int
    article_count: int
    lon: float
    lat: float
    pinned: bool = Field(description="True: su propio punto; False: junto al lugar de sus notas.")
    first_seen: datetime | None
    last_seen: datetime | None

    @classmethod
    def from_node(cls, n: GraphNode) -> "GraphNodeOut":
        """Convierte el nodo del caso de uso."""
        e = n.entity
        return cls(
            id=e.entity_id,
            type=e.type.value,
            type_label=ENTITY_TYPE_LABEL[e.type],
            label=e.label,
            legal_status=e.legal_status,
            legal_status_label=LEGAL_STATUS_LABEL[e.legal_status] if e.legal_status else None,
            mention_count=len(e.mentions),
            article_count=e.article_count,
            lon=n.position.lon,
            lat=n.position.lat,
            pinned=n.pinned,
            first_seen=n.first_seen,
            last_seen=n.last_seen,
        )


class GraphNoteOut(BaseModel):
    """Una nota del caso en la constelación."""

    article_id: int
    title: str
    url: str
    published_at: datetime | None
    lon: float
    lat: float
    entity_ids: list[int]

    @classmethod
    def from_note(cls, n: GraphNote) -> "GraphNoteOut":
        """Convierte la nota del caso de uso."""
        return cls(
            article_id=n.article_id,
            title=n.title,
            url=n.url,
            published_at=n.published_at,
            lon=n.position.lon,
            lat=n.position.lat,
            entity_ids=list(n.entity_ids),
        )


class NoteLinkOut(BaseModel):
    """Dos notas que comparten entidades confirmadas."""

    first: int
    second: int
    shared: int


class CaseGraphOut(BaseModel):
    """Respuesta de ``GET /cases/{id}/graph``."""

    case_id: UUID
    name: str
    center: PointOut
    hidden_nodes: int = Field(description="Confirmadas que no caben en el tope («+N más»).")
    nodes: list[GraphNodeOut]
    edges: list[RelationshipOut]
    notes: list[GraphNoteOut]
    note_links: list[NoteLinkOut]

    @classmethod
    def from_graph(cls, g: CaseGraph) -> "CaseGraphOut":
        """Convierte el muro del caso de uso."""
        return cls(
            case_id=g.case_id,
            name=g.name,
            center=PointOut(lon=g.center.lon, lat=g.center.lat),
            hidden_nodes=g.hidden_nodes,
            nodes=[GraphNodeOut.from_node(n) for n in g.nodes],
            edges=[RelationshipOut.from_view(r) for r in g.edges],
            notes=[GraphNoteOut.from_note(n) for n in g.notes],
            note_links=[
                NoteLinkOut(first=a, second=b, shared=shared)
                for (a, b), shared in sorted(g.note_links.items())
            ],
        )


class CaseOnMapOut(BaseModel):
    """Un caso de la persona en el globo."""

    id: UUID
    name: str
    sensitivity: Sensitivity
    sensitivity_label: str
    article_count: int
    confirmed_count: int
    lon: float
    lat: float

    @classmethod
    def from_case(cls, c: CaseOnMap) -> "CaseOnMapOut":
        """Convierte el caso del caso de uso (solo casos ubicados).

        Raises:
            ValueError: Si el caso no tiene ubicación (el caso de uso los filtra).
        """
        if c.point is None:
            raise ValueError("Solo se muestran casos con ubicación.")
        sensitivity = Sensitivity(c.sensitivity)
        return cls(
            id=c.case_id,
            name=c.name,
            sensitivity=sensitivity,
            sensitivity_label=SENSITIVITY_LABEL[sensitivity],
            article_count=c.article_count,
            confirmed_count=c.confirmed_count,
            lon=c.point.lon,
            lat=c.point.lat,
        )


class CasesOnMapOut(BaseModel):
    """Respuesta de ``GET /cases/map``."""

    items: list[CaseOnMapOut]
