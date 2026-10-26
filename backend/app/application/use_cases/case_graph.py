"""Casos de uso del muro de un caso sobre el globo (Fase 9.6, historia H9.3).

- ``GetCaseGraph``: arma lo que dibuja el globo: nodos (solo entidades
  confirmadas, ADR-0104) con su posición, arcos (los vínculos de la 9.5 que
  no se descartaron) y, para la constelación, las notas con sus enlaces.
  Abrir el muro cuenta como ver el caso (§9.10).
- ``ListCasesOnMap``: los casos abiertos de la persona con su centro, para
  «Mis casos» en el globo.

No hace: no sabe de HTTP, SQL ni MapLibre; no calcula posiciones (eso es
``app.domain.case_graph``).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.audit import Actor, AuditEntry
from app.application.ports.case_graph import CaseGraphRepositoryPort, CaseOnMap
from app.application.ports.cases import CaseRepositoryPort
from app.application.ports.entities import CaseEntity, EntityRepositoryPort
from app.application.ports.relationships import RelationshipRepositoryPort, RelationshipView
from app.application.use_cases.cases import CASE_VIEW_DEDUP_MINUTES, case_for
from app.domain.case_graph import (
    GeoPoint,
    LayoutItem,
    case_center,
    layout_points,
    node_anchor,
    note_links,
    visible_nodes,
)
from app.domain.investigation import InvestigationAction, ReviewStatus


@dataclass(frozen=True, slots=True)
class GraphNode:
    """Una entidad confirmada en el muro.

    Attributes:
        entity: La entidad con su evidencia.
        position: Dónde se dibuja.
        pinned: Si es su propio punto (un lugar) o una posición visual
            alrededor del lugar de sus notas.
        first_seen: Fecha de la nota más vieja donde aparece.
        last_seen: Fecha de la más reciente.
    """

    entity: CaseEntity
    position: GeoPoint
    pinned: bool
    first_seen: datetime | None
    last_seen: datetime | None


@dataclass(frozen=True, slots=True)
class GraphNote:
    """Una nota del caso en la constelación.

    Attributes:
        article_id: Nota.
        title: Título.
        url: Liga a la nota original.
        published_at: Fecha.
        position: Dónde se dibuja.
        entity_ids: Entidades confirmadas visibles que aparecen en ella.
    """

    article_id: int
    title: str
    url: str
    published_at: datetime | None
    position: GeoPoint
    entity_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CaseGraph:
    """Lo que el globo dibuja de un caso.

    Attributes:
        case_id: Caso.
        name: Nombre del caso.
        center: Centro de sus notas.
        nodes: Entidades confirmadas visibles.
        hidden_nodes: Confirmadas que quedaron fuera por el tope.
        edges: Vínculos entre nodos visibles (confirmados y sugeridos).
        notes: Notas ubicadas (constelación).
        note_links: Pares de notas que comparten entidades, con cuántas.
    """

    case_id: UUID
    name: str
    center: GeoPoint
    nodes: tuple[GraphNode, ...]
    hidden_nodes: int
    edges: tuple[RelationshipView, ...]
    notes: tuple[GraphNote, ...]
    note_links: dict[tuple[int, int], int]


class GetCaseGraph:
    """Arma el muro de un caso y registra que la persona lo vio."""

    def __init__(
        self,
        *,
        cases: CaseRepositoryPort,
        entities: EntityRepositoryPort,
        relationships: RelationshipRepositoryPort,
        points: CaseGraphRepositoryPort,
        max_nodes: int,
    ) -> None:
        """Recibe las piezas.

        Args:
            cases: Casos (permisos y bitácora).
            entities: Entidades del caso.
            relationships: Vínculos del caso.
            points: Puntos del catálogo.
            max_nodes: Tope de nodos visibles (``CASE_MAX_VISIBLE_NODES``).
        """
        self._cases = cases
        self._entities = entities
        self._relationships = relationships
        self._points = points
        self._max_nodes = max_nodes

    async def execute(self, case_id: UUID, actor: Actor) -> CaseGraph:
        """Devuelve el muro del caso.

        Args:
            case_id: Caso.
            actor: Quién lo abre (cualquier miembro).

        Returns:
            Nodos con posición, arcos y la constelación.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
        """
        view = await case_for(self._cases, case_id, actor)
        await self._cases.record_view(
            case_id,
            AuditEntry(actor, InvestigationAction.CASE_VIEWED, {"view": "wall"}),
            CASE_VIEW_DEDUP_MINUTES,
        )
        confirmed = {
            e.entity_id: e
            for e in await self._entities.list_entities(case_id, ReviewStatus.CONFIRMED)
        }
        shown, hidden = visible_nodes(
            {entity_id: len(e.mentions) for entity_id, e in confirmed.items()}, self._max_nodes
        )
        points = await self._points.points(case_id, shown)
        note_points = {n.article_id: n.point for n in points.notes if n.point is not None}
        center = case_center(note_points.values())
        nodes = self._nodes(
            [confirmed[i] for i in shown], points.entity_points, note_points, center
        )
        visible = set(shown)
        edges = tuple(
            r
            for r in await self._relationships.list_case(case_id)
            if r.review_status is not ReviewStatus.DISCARDED
            and r.entity_a.entity_id in visible
            and r.entity_b.entity_id in visible
        )
        entities_by_note: dict[int, set[int]] = {}
        for node in nodes:
            for mention in node.entity.mentions:
                entities_by_note.setdefault(mention.article_id, set()).add(node.entity.entity_id)
        located = [n for n in points.notes if n.point is not None]
        note_positions = layout_points(
            [
                LayoutItem(
                    n.article_id, n.point, False, len(entities_by_note.get(n.article_id, ()))
                )
                for n in located
                if n.point is not None
            ]
        )
        notes = tuple(
            GraphNote(
                article_id=n.article_id,
                title=n.title,
                url=n.url,
                published_at=n.published_at,
                position=note_positions[n.article_id],
                entity_ids=tuple(sorted(entities_by_note.get(n.article_id, ()))),
            )
            for n in located
        )
        return CaseGraph(
            case_id=case_id,
            name=view.case.name,
            center=center,
            nodes=nodes,
            hidden_nodes=hidden,
            edges=edges,
            notes=notes,
            note_links=note_links({n.article_id: set(n.entity_ids) for n in notes if n.entity_ids}),
        )

    @staticmethod
    def _nodes(
        entities: list[CaseEntity],
        entity_points: dict[int, GeoPoint],
        note_points: dict[int, GeoPoint],
        center: GeoPoint,
    ) -> tuple[GraphNode, ...]:
        items: list[LayoutItem] = []
        for entity in entities:
            article_points = [
                note_points[m.article_id] for m in entity.mentions if m.article_id in note_points
            ]
            anchor, pinned = node_anchor(
                entity.type, entity_points.get(entity.entity_id), article_points, center
            )
            items.append(LayoutItem(entity.entity_id, anchor, pinned, len(entity.mentions)))
        positions = layout_points(items)
        # Un lugar que tuvo que moverse (compartía punto con otro) ya no es "su punto".
        pinned_ids = {i.item_id for i in items if i.pinned and positions[i.item_id] == i.anchor}
        nodes = []
        for entity in entities:
            dates = [m.published_at for m in entity.mentions if m.published_at is not None]
            nodes.append(
                GraphNode(
                    entity=entity,
                    position=positions[entity.entity_id],
                    pinned=entity.entity_id in pinned_ids,
                    first_seen=min(dates) if dates else None,
                    last_seen=max(dates) if dates else None,
                )
            )
        return tuple(nodes)


class ListCasesOnMap:
    """Los casos abiertos de la persona, con su centro para el globo (D9)."""

    def __init__(self, points: CaseGraphRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            points: Puntos del catálogo.
        """
        self._points = points

    async def execute(self, actor: Actor) -> list[CaseOnMap]:
        """Lista los casos ubicados de la persona, por nombre.

        Mirar el mapa de casos no abre ninguno: no va a la bitácora como vista.

        Args:
            actor: Quién pregunta (solo ve sus casos).

        Returns:
            Sus casos abiertos con al menos una nota ubicada.
        """
        found = await self._points.cases_on_map(actor.user_id)
        return sorted(
            (c for c in found if c.point is not None), key=lambda c: (c.name.casefold(), c.case_id)
        )
