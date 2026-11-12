"""Entidades de los casos en memoria y una IA falsa, para pruebas unitarias (Fase 9.4).

``FakeEntityRepository`` imita lo que garantiza PostgreSQL en lo que importa a
los casos de uso: el estado de cada nota del caso, una lectura guardada por
nota y versión de prompt, la revisión firmada de cada entidad y, desde la
9.5, las fusiones, separaciones y descartes de fusión. No agrupa
propuestas ni calcula sugerencias de fusión: la prueba las pone en
``suggestions`` (eso lo prueban las pruebas de integración del repositorio
real).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID

from app.application.audit import AuditEntry
from app.application.ports.entities import (
    ArticleSource,
    CaseAnalysis,
    CaseEntity,
    EntityReview,
    FailedExtraction,
    Materialized,
    MergedEntity,
    MergeSuggestion,
    StoredExtraction,
)
from app.application.ports.llm import (
    EntityExtractionError,
    EntityExtractionRequest,
    EntityExtractionResult,
)
from app.domain.enrichment import LLMUsage
from app.domain.entity_extraction import CaseArticleEntitiesStatus, RawProposal
from app.domain.entity_resolution import MergeCandidate
from app.domain.errors import EntityNotFoundError
from app.domain.investigation import LegalStatus, ReviewStatus

REVIEWED_AT = datetime(2026, 10, 21, 19, tzinfo=UTC)


@dataclass
class Materialization:
    """Una llamada a ``materialize``: qué se guardó en el caso y con qué bitácora."""

    case_id: UUID
    extraction: StoredExtraction
    cost_usd: float
    audit: AuditEntry


@dataclass
class FakeEntityRepository:
    """Implementa ``EntityRepositoryPort`` con diccionarios."""

    sources: dict[tuple[UUID, int], ArticleSource] = field(default_factory=dict)
    extractions: dict[tuple[int, str], StoredExtraction] = field(default_factory=dict)
    failures: list[tuple[UUID, FailedExtraction, AuditEntry]] = field(default_factory=list)
    materialized: list[Materialization] = field(default_factory=list)
    entities: dict[UUID, dict[int, CaseEntity]] = field(default_factory=dict)
    reviews: list[tuple[UUID, AuditEntry]] = field(default_factory=list)
    costs: dict[tuple[UUID, int], float] = field(default_factory=dict)
    saved: int = 0
    # Fase 9.5: fusiones, sugerencias que pone la prueba y descartes.
    merged_into: dict[tuple[UUID, int], int] = field(default_factory=dict)
    suggestions: list[MergeSuggestion] = field(default_factory=list)
    dismissed: set[tuple[UUID, int, int]] = field(default_factory=set)
    resolution_audits: list[AuditEntry] = field(default_factory=list)
    next_id: int = 1000
    # F12 (ADR-0107): cuántas revisiones en bloque llegaron al repositorio.
    bulk_calls: int = 0

    def add_article(
        self,
        case_id: UUID,
        article_id: int,
        *,
        body: str | None = "Un juez giró orden de aprehensión contra Julián Ortega Ruiz.",
        snippet: str | None = "Fragmento del medio.",
        status: CaseArticleEntitiesStatus = CaseArticleEntitiesStatus.PENDING,
        full_text: bool = True,
    ) -> None:
        """Atajo de las pruebas: una nota en el caso."""
        self.sources[(case_id, article_id)] = ArticleSource(
            article_id=article_id,
            status=status,
            title=f"Nota {article_id}: orden de aprehensión en Polanco",
            snippet=snippet,
            stored_body=body,
            full_text=full_text,
            published_at=datetime(2026, 10, 9, tzinfo=UTC),
        )

    def add_entity(self, case_id: UUID, entity: CaseEntity) -> None:
        """Atajo de las pruebas: una entidad en el caso."""
        self.entities.setdefault(case_id, {})[entity.entity_id] = entity

    def status_of(self, case_id: UUID, article_id: int) -> CaseArticleEntitiesStatus:
        """Estado de análisis de una nota del caso."""
        return self.sources[(case_id, article_id)].status

    def _set(self, case_id: UUID, article_id: int, status: CaseArticleEntitiesStatus) -> None:
        key = (case_id, article_id)
        if key in self.sources and self.sources[key].status is not CaseArticleEntitiesStatus.DONE:
            self.sources[key] = replace(self.sources[key], status=status)

    async def article_source(self, case_id: UUID, article_id: int) -> ArticleSource | None:
        return self.sources.get((case_id, article_id))

    async def done_count(self, case_id: UUID) -> int:
        return sum(
            1
            for (case, _), s in self.sources.items()
            if case == case_id and s.status is CaseArticleEntitiesStatus.DONE
        )

    async def get_extraction(self, article_id: int, prompt_version: str) -> StoredExtraction | None:
        return self.extractions.get((article_id, prompt_version))

    async def save_extraction(self, extraction: StoredExtraction) -> None:
        self.saved += 1
        self.extractions[(extraction.article_id, extraction.prompt_version)] = extraction

    async def save_failure(
        self, case_id: UUID, failure: FailedExtraction, audit: AuditEntry
    ) -> None:
        self.failures.append((case_id, failure, audit))
        self._set(case_id, failure.article_id, CaseArticleEntitiesStatus.FAILED)
        key = (case_id, failure.article_id)
        self.costs[key] = self.costs.get(key, 0.0) + failure.cost_usd

    async def materialize(
        self, case_id: UUID, extraction: StoredExtraction, cost_usd: float, audit: AuditEntry
    ) -> Materialized | None:
        key = (case_id, extraction.article_id)
        if key not in self.sources:
            return None
        self.materialized.append(Materialization(case_id, extraction, cost_usd, audit))
        self.sources[key] = replace(self.sources[key], status=CaseArticleEntitiesStatus.DONE)
        self.costs[key] = self.costs.get(key, 0.0) + cost_usd
        return Materialized(len(extraction.reviewed.proposals), 0, 0)

    async def set_status(
        self, case_id: UUID, article_ids: Sequence[int], status: CaseArticleEntitiesStatus
    ) -> None:
        for article_id in article_ids:
            self._set(case_id, article_id, status)

    async def to_analyze(self, case_id: UUID, limit: int) -> list[int]:
        todo = (CaseArticleEntitiesStatus.PENDING, CaseArticleEntitiesStatus.FAILED)
        return sorted(
            article
            for (case, article), s in self.sources.items()
            if case == case_id and s.status in todo
        )[:limit]

    async def analysis(self, case_id: UUID) -> CaseAnalysis:
        statuses = [s.status for (case, _), s in self.sources.items() if case == case_id]
        count = {status: statuses.count(status) for status in CaseArticleEntitiesStatus}
        return CaseAnalysis(
            articles=len(statuses),
            pending=count[CaseArticleEntitiesStatus.PENDING],
            queued=count[CaseArticleEntitiesStatus.QUEUED],
            done=count[CaseArticleEntitiesStatus.DONE],
            failed=count[CaseArticleEntitiesStatus.FAILED],
            skipped=count[CaseArticleEntitiesStatus.SKIPPED],
            title_snippet=0,
            cost_usd=sum(cost for (case, _), cost in self.costs.items() if case == case_id),
        )

    async def list_entities(self, case_id: UUID, status: ReviewStatus) -> list[CaseEntity]:
        return [
            e
            for e in self.entities.get(case_id, {}).values()
            if e.review_status is status and (case_id, e.entity_id) not in self.merged_into
        ]

    async def review_counts(self, case_id: UUID) -> dict[ReviewStatus, int]:
        found = list(self.entities.get(case_id, {}).values())
        return {s: sum(1 for e in found if e.review_status is s) for s in ReviewStatus}

    async def get_entity(self, case_id: UUID, entity_id: int) -> CaseEntity | None:
        if (case_id, entity_id) in self.merged_into:
            return None
        return self.entities.get(case_id, {}).get(entity_id)

    async def review(
        self,
        case_id: UUID,
        entity_id: int,
        *,
        status: ReviewStatus,
        legal_status: LegalStatus | None,
        reviewer: str,
        audit: AuditEntry,
    ) -> CaseEntity:
        reviewed = replace(
            self.entities[case_id][entity_id],
            review_status=status,
            legal_status=legal_status,
            reviewed_by=reviewer,
            reviewed_at=REVIEWED_AT,
        )
        self.entities[case_id][entity_id] = reviewed
        self.reviews.append((case_id, audit))
        return reviewed

    async def get_entities(self, case_id: UUID, entity_ids: Sequence[int]) -> list[CaseEntity]:
        found = [await self.get_entity(case_id, entity_id) for entity_id in entity_ids]
        return [entity for entity in found if entity is not None]

    async def review_many(
        self, case_id: UUID, reviews: Sequence[EntityReview], *, reviewer: str
    ) -> None:
        # Todo o nada, como la transacción de PostgreSQL.
        found = await self.get_entities(case_id, [r.entity_id for r in reviews])
        if len(found) != len(reviews):
            raise EntityNotFoundError("No existe esa entidad en el caso.", {})
        for r in reviews:
            await self.review(
                case_id,
                r.entity_id,
                status=r.status,
                legal_status=r.legal_status,
                reviewer=reviewer,
                audit=r.audit,
            )
        self.bulk_calls += 1

    async def merge_suggestions(self, case_id: UUID) -> list[MergeSuggestion]:
        return [
            s
            for s in self.suggestions
            if (case_id, s.first.entity_id, s.second.entity_id) not in self.dismissed
        ]

    async def merge_candidate(self, case_id: UUID, entity_id: int) -> MergeCandidate | None:
        entity = self.entities.get(case_id, {}).get(entity_id)
        if entity is None:
            return None
        return MergeCandidate(
            entity_id, entity.type, entity.review_status, self.merged_into.get((case_id, entity_id))
        )

    async def merge(
        self, case_id: UUID, keep_id: int, merge_id: int, audit: AuditEntry
    ) -> CaseEntity:
        keep, merge = self.entities[case_id][keep_id], self.entities[case_id][merge_id]
        self.merged_into[(case_id, merge_id)] = keep_id
        kept = replace(
            keep,
            mentions=keep.mentions + merge.mentions,
            merged=(*keep.merged, MergedEntity(merge_id, merge.label, keep_id)),
        )
        self.entities[case_id][keep_id] = kept
        self.resolution_audits.append(audit)
        return kept

    async def unmerge(self, case_id: UUID, entity_id: int, audit: AuditEntry) -> CaseEntity:
        self.merged_into.pop((case_id, entity_id))
        self.resolution_audits.append(audit)
        return self.entities[case_id][entity_id]

    async def split(
        self, case_id: UUID, entity_id: int, mention_ids: Sequence[int], audit: AuditEntry
    ) -> CaseEntity:
        source = self.entities[case_id][entity_id]
        self.next_id += 1
        moved = tuple(
            replace(m, entity_id=self.next_id)
            for m in source.mentions
            if m.mention_id in mention_ids
        )
        created = replace(
            source,
            entity_id=self.next_id,
            label=moved[0].mention_text,
            aliases=(),
            review_status=ReviewStatus.SUGGESTED,
            legal_status=None,
            reviewed_by=None,
            reviewed_at=None,
            mentions=moved,
            merged=(),
        )
        self.entities[case_id][entity_id] = replace(
            source, mentions=tuple(m for m in source.mentions if m.mention_id not in mention_ids)
        )
        self.entities[case_id][self.next_id] = created
        self.resolution_audits.append(audit)
        return created

    async def dismiss_merge(
        self, case_id: UUID, first_id: int, second_id: int, audit: AuditEntry
    ) -> bool:
        key = (case_id, first_id, second_id)
        if key in self.dismissed:
            return False
        self.dismissed.add(key)
        self.resolution_audits.append(audit)
        return True


@dataclass
class FakeEntityQueue:
    """``EntityQueuePort`` que solo anota lo encolado."""

    queued: list[tuple[UUID, int, str]] = field(default_factory=list)

    def enqueue(self, case_id: UUID, article_id: int, requested_by: str) -> None:
        self.queued.append((case_id, article_id, requested_by))


@dataclass
class FakeExtractor:
    """``EntityExtractorPort`` que responde lo que le den (o falla)."""

    proposals: tuple[RawProposal, ...] = ()
    usage: LLMUsage = field(default_factory=lambda: LLMUsage(2000, 600))
    error: Exception | None = None
    requests: list[EntityExtractionRequest] = field(default_factory=list)

    @property
    def model(self) -> str:
        return "gpt-6-luna"

    @property
    def entities_prompt_version(self) -> str:
        return "entities_v1"

    async def aclose(self) -> None:
        return None

    async def extract_entities(self, request: EntityExtractionRequest) -> EntityExtractionResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return EntityExtractionResult(self.proposals, self.usage, self.model, "entities_v1")


def failing_extractor(tokens_in: int = 3000, tokens_out: int = 20) -> FakeExtractor:
    """Una IA que no da un JSON válido tras reintentar."""
    usage = LLMUsage(tokens_in, tokens_out)
    return FakeExtractor(error=EntityExtractionError("JSON inválido tras reintentar", usage))
