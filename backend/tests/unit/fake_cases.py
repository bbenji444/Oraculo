"""Repositorio de casos en memoria para pruebas unitarias (sin base de datos).

Imita las reglas que garantiza PostgreSQL: un caso solo existe para sus
miembros, quien lo crea queda como dueño, y ``case.viewed`` se registra una
vez por persona y ventana de minutos.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.audit import AuditEntry
from app.application.pagination import TimeCursor
from app.domain.case import Case, CaseDraft, CaseView
from app.domain.investigation import CaseMemberRole, CaseStatus

START = datetime(2026, 10, 21, 18, tzinfo=UTC)


class FakeCaseRepository:
    """Implementa ``CaseRepositoryPort`` con diccionarios."""

    def __init__(self) -> None:
        self.cases: dict[UUID, Case] = {}
        self.members: dict[UUID, dict[str, CaseMemberRole]] = {}
        self.audit: list[tuple[UUID, AuditEntry, datetime]] = []
        self.now = START

    def tick(self, minutes: int) -> None:
        """Avanza el reloj de la base falsa."""
        self.now += timedelta(minutes=minutes)

    def add_member(self, case_id: UUID, user: str, role: CaseMemberRole) -> None:
        """Atajo de las pruebas para dar acceso a otra persona."""
        self.members[case_id][user] = role

    async def create(self, data: CaseDraft, created_by: str, audit: AuditEntry) -> Case:
        self.tick(1)
        case = Case(
            id=uuid4(),
            name=data.name,
            description=data.description,
            status=CaseStatus.OPEN,
            sensitivity=data.sensitivity,
            created_by=created_by,
            closed_at=None,
            created_at=self.now,
            updated_at=self.now,
            article_count=0,
        )
        self.cases[case.id] = case
        self.members[case.id] = {created_by: CaseMemberRole.OWNER}
        self.audit.append((case.id, audit, self.now))
        return case

    async def get_view(self, case_id: UUID, user_id: str) -> CaseView | None:
        role = self.members.get(case_id, {}).get(user_id)
        if role is None:
            return None
        return CaseView(self.cases[case_id], role)

    async def list_for_user(
        self,
        user_id: str,
        statuses: Sequence[CaseStatus],
        contains_article: int | None,
        after: TimeCursor | None,
        limit: int,
    ) -> list[CaseView]:
        mine = [
            CaseView(case, self.members[case.id][user_id])
            for case in self.cases.values()
            if user_id in self.members[case.id] and case.status in statuses
        ]
        mine.sort(key=lambda v: (v.case.updated_at, str(v.case.id)), reverse=True)
        if after is not None and after.moment is not None:
            key = (after.moment, after.id)
            mine = [v for v in mine if (v.case.updated_at, str(v.case.id)) < key]
        if contains_article is not None:
            mine = [replace(v, has_article=False) for v in mine]
        return mine[:limit]

    async def update(
        self,
        case_id: UUID,
        *,
        data: CaseDraft,
        status: CaseStatus,
        closed_at: datetime | None,
        audit: AuditEntry,
    ) -> Case:
        self.tick(1)
        case = replace(
            self.cases[case_id],
            name=data.name,
            description=data.description,
            sensitivity=data.sensitivity,
            status=status,
            closed_at=closed_at,
            updated_at=self.now,
        )
        self.cases[case_id] = case
        self.audit.append((case_id, audit, self.now))
        return case

    async def record_view(self, case_id: UUID, audit: AuditEntry, window_minutes: int) -> bool:
        since = self.now - timedelta(minutes=window_minutes)
        recent = any(
            cid == case_id
            and entry.action == audit.action
            and entry.actor.user_id == audit.actor.user_id
            and moment > since
            for cid, entry, moment in self.audit
        )
        if recent:
            return False
        self.audit.append((case_id, audit, self.now))
        return True
