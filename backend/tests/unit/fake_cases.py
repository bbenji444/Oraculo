"""Repositorio de casos en memoria para pruebas unitarias (sin base de datos).

Imita las reglas que garantiza PostgreSQL: un caso solo existe para sus
miembros, quien lo crea queda como dueño, ``case.viewed`` se registra una
vez por persona y ventana de minutos, y una noticia entra una sola vez.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.audit import AuditEntry
from app.application.pagination import TimeCursor
from app.application.ports.search_reads import ArticleItem
from app.domain.case import Case, CaseDraft, CaseMember, CaseView
from app.domain.investigation import CaseMemberRole, CaseStatus

START = datetime(2026, 10, 21, 18, tzinfo=UTC)


class FakeCaseRepository:
    """Implementa ``CaseRepositoryPort`` con diccionarios."""

    def __init__(self) -> None:
        self.cases: dict[UUID, Case] = {}
        self.members: dict[UUID, dict[str, CaseMemberRole]] = {}
        self.audit: list[tuple[UUID, AuditEntry, datetime]] = []
        self.articles: dict[int, ArticleItem] = {}
        self.case_articles: dict[UUID, list[int]] = {}
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

    def known_article(self, article_id: int, title: str, published: datetime | None) -> None:
        """Atajo de las pruebas para que exista una noticia."""
        self.articles[article_id] = ArticleItem(
            article_id=article_id,
            title=title,
            source_name="Milenio",
            source_domain="milenio.com",
            url=f"https://milenio.com/{article_id}",
            published_at=published,
            summary="Resumen.",
            event_type="homicidio",
            event_date=None,
            extraction_status="ok",
            enrichment_status="ok",
            judgements=(),
            primary=None,
            in_region=None,
            providers=("searchapi",),
        )

    def _recount(self, case_id: UUID) -> None:
        self.tick(1)
        self.cases[case_id] = replace(
            self.cases[case_id],
            article_count=len(self.case_articles.get(case_id, [])),
            updated_at=self.now,
        )

    async def article_exists(self, article_id: int) -> bool:
        return article_id in self.articles

    async def add_article(
        self, case_id: UUID, article_id: int, added_by: str, audit: AuditEntry
    ) -> bool:
        items = self.case_articles.setdefault(case_id, [])
        if article_id in items:
            return False
        items.append(article_id)
        self._recount(case_id)
        self.audit.append((case_id, audit, self.now))
        return True

    async def remove_article(self, case_id: UUID, article_id: int, audit: AuditEntry) -> bool:
        items = self.case_articles.get(case_id, [])
        if article_id not in items:
            return False
        items.remove(article_id)
        self._recount(case_id)
        self.audit.append((case_id, audit, self.now))
        return True

    async def list_articles(
        self, case_id: UUID, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        notes = [self.articles[i] for i in self.case_articles.get(case_id, [])]
        notes.sort(key=lambda a: (a.published_at or START, a.article_id), reverse=True)
        if after is not None and after.moment is not None:
            key = (after.moment, int(after.id))
            notes = [a for a in notes if (a.published_at or START, a.article_id) < key]
        return notes[:limit]

    async def list_members(self, case_id: UUID) -> list[CaseMember]:
        members = self.members.get(case_id, {})
        return [
            CaseMember(user, role, "benji", self.now)
            for user, role in sorted(
                members.items(), key=lambda m: (m[1] is not CaseMemberRole.OWNER, m[0])
            )
        ]

    async def save_member(self, case_id: UUID, member: CaseMember, audit: AuditEntry) -> bool:
        current = self.members[case_id].get(member.user_id)
        if current in (member.role, CaseMemberRole.OWNER):
            return False
        self.members[case_id][member.user_id] = member.role
        self.audit.append((case_id, audit, self.now))
        return True

    async def remove_member(self, case_id: UUID, user_id: str, audit: AuditEntry) -> bool:
        if self.members[case_id].get(user_id) in (None, CaseMemberRole.OWNER):
            return False
        del self.members[case_id][user_id]
        self.audit.append((case_id, audit, self.now))
        return True
