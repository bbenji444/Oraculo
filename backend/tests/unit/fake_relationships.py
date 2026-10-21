"""Vínculos de los casos en memoria, para pruebas unitarias (Fase 9.5).

``FakeRelationshipRepository`` devuelve los vínculos que la prueba ponga en
``views`` (como si ya se hubieran calculado o guardado) y aplica lo que se
guarda. No calcula coocurrencias: eso lo prueban las pruebas de integración
del repositorio real.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID

from app.application.audit import AuditEntry
from app.application.ports.relationships import (
    RelationshipEnd,
    RelationshipView,
    RelationshipWrite,
    find,
)
from app.domain.investigation import EntityType, LegalStatus, Origin, RelationshipType, ReviewStatus

REVIEWED_AT = datetime(2026, 10, 21, 20, tzinfo=UTC)


def end(entity_id: int, kind: EntityType = EntityType.PERSON) -> RelationshipEnd:
    """Una punta de vínculo de prueba."""
    legal = LegalStatus.ALLEGED if kind is EntityType.PERSON else None
    return RelationshipEnd(entity_id, kind, f"Entidad {entity_id}", legal)


def suggested(first: int, second: int, shared: int = 1) -> RelationshipView:
    """Un «aparecen juntas» calculado y sin revisar (sin id)."""
    return RelationshipView(
        relationship_id=None,
        entity_a=end(first),
        entity_b=end(second),
        type=RelationshipType.APPEARS_WITH,
        custom_label=None,
        origin=Origin.COOCCURRENCE,
        confidence={1: 0.5, 2: 0.7}.get(shared, 0.9),
        review_status=ReviewStatus.SUGGESTED,
        reviewed_by=None,
        reviewed_at=None,
        notes=None,
        shared_articles=(),
    )


@dataclass
class FakeRelationshipRepository:
    """Implementa ``RelationshipRepositoryPort`` con una lista por caso."""

    views: dict[UUID, list[RelationshipView]] = field(default_factory=dict)
    saved: list[tuple[UUID, RelationshipWrite, AuditEntry]] = field(default_factory=list)
    next_id: int = 500

    async def list_case(self, case_id: UUID) -> list[RelationshipView]:
        return list(self.views.get(case_id, []))

    async def save(self, case_id: UUID, write: RelationshipWrite, audit: AuditEntry) -> None:
        self.saved.append((case_id, write, audit))
        views = self.views.setdefault(case_id, [])
        current = find(views, write.key)
        if current is None:
            self.next_id += 1
            current = replace(
                suggested(write.key.entity_a, write.key.entity_b),
                type=write.key.type,
                origin=write.origin,
                confidence=write.confidence,
            )
        else:
            views.remove(current)
        relationship_id = write.relationship_id or current.relationship_id or self.next_id
        views.append(
            replace(
                current,
                relationship_id=relationship_id,
                custom_label=write.custom_label,
                review_status=write.review_status,
                reviewed_by=write.reviewer,
                reviewed_at=REVIEWED_AT,
                notes=write.notes if write.notes is not None else current.notes,
            )
        )
