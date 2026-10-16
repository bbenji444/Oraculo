"""Repositorio de conceptos en memoria para pruebas unitarias (sin base de datos)."""

from datetime import UTC, datetime

from app.application.audit import AuditEntry
from app.application.pagination import NameCursor
from app.domain.concept import Concept, ConceptDraft
from app.domain.errors import ConceptNotFoundError

NOW = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)


class FakeConceptRepository:
    """Implementa ``ConceptRepositoryPort`` con un diccionario en memoria."""

    def __init__(self) -> None:
        self.concepts: dict[int, Concept] = {}
        self.deleted: dict[int, Concept] = {}
        self.audit: list[tuple[int, AuditEntry]] = []
        self.used_in_searches: set[int] = set()
        self._next_id = 1

    def add(self, data: ConceptDraft, created_by: str = "prueba") -> Concept:
        concept = Concept(self._next_id, data, created_by, NOW, NOW)
        self.concepts[concept.id] = concept
        self._next_id += 1
        return concept

    async def list_concepts(
        self, active: bool | None, after: NameCursor | None, limit: int
    ) -> list[Concept]:
        rows = [c for c in self.concepts.values() if active is None or c.data.is_active is active]
        rows.sort(key=lambda c: (c.data.name_norm, c.id))
        if after:
            rows = [c for c in rows if (c.data.name_norm, c.id) > (after.name_norm, after.id)]
        return rows[:limit]

    async def get(self, concept_id: int) -> Concept | None:
        return self.concepts.get(concept_id)

    async def name_taken(self, name_norm: str, except_id: int | None) -> bool:
        return any(
            c.data.name_norm == name_norm and c.id != except_id for c in self.concepts.values()
        )

    async def create(self, data: ConceptDraft, created_by: str, audit: AuditEntry) -> Concept:
        concept = self.add(data, created_by)
        self.audit.append((concept.id, audit))
        return concept

    async def update(self, concept_id: int, data: ConceptDraft, audit: AuditEntry) -> Concept:
        if concept_id not in self.concepts:
            raise ConceptNotFoundError("No existe ese concepto.")
        current = self.concepts[concept_id]
        updated = Concept(concept_id, data, current.created_by, current.created_at, NOW)
        self.concepts[concept_id] = updated
        self.audit.append((concept_id, audit))
        return updated

    async def delete(self, concept_id: int, *, logical: bool, audit: AuditEntry) -> None:
        concept = self.concepts.pop(concept_id)
        if logical:
            self.deleted[concept_id] = concept
        self.audit.append((concept_id, audit))

    async def is_used_in_searches(self, concept_id: int) -> bool:
        return concept_id in self.used_in_searches
