"""``CaseRepositoryPort`` sobre PostgreSQL (Fase 9.3; tablas de la migración 0019).

Cada lectura une ``cases`` con ``case_members`` de la persona que pregunta:
un caso del que no es miembro no aparece nunca (decisión D3 de la 9.3). Cada
escritura guarda su registro en ``audit_log`` en la misma transacción.

``case.viewed`` se escribe con un ``INSERT ... WHERE NOT EXISTS`` que mira la
bitácora de los últimos minutos (índice ``audit_log_entity``): una sola
consulta, sin carreras entre dos pestañas que abren el caso a la vez.

No hace: no valida reglas ni permisos (eso es el dominio y los casos de uso).
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.adapters.persistence.article_rows import (
    ALL_JUDGEMENTS,
    ALL_PROVIDERS,
    ARTICLE_COLUMNS,
    PRIMARY_COLUMNS,
    article_item,
)
from app.application.audit import AuditEntry
from app.application.pagination import TimeCursor
from app.application.ports.search_reads import ArticleItem
from app.domain.case import Case, CaseDraft, CaseMember, CaseView
from app.domain.investigation import CaseMemberRole, CaseStatus, Sensitivity

# ``audit_log.entity_type`` de todo lo que pasa en un caso.
ENTITY_TYPE = "case"

_COLUMNS = """
    c.id, c.name, c.description, c.status, c.sensitivity, c.created_by, c.closed_at,
    c.created_at, c.updated_at, c.deleted_at,
    (SELECT count(*) FROM case_articles ca WHERE ca.case_id = c.id) AS article_count
"""


def _to_case(row: RowMapping) -> Case:
    return Case(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        status=CaseStatus(row["status"]),
        sensitivity=Sensitivity(row["sensitivity"]),
        created_by=row["created_by"],
        closed_at=row["closed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        article_count=int(row["article_count"]),
        deleted_at=row["deleted_at"],
    )


def _to_view(row: RowMapping) -> CaseView:
    return CaseView(
        case=_to_case(row),
        role=CaseMemberRole(row["role"]),
        has_article=row.get("has_article"),
    )


async def write_audit(conn: AsyncConnection, case_id: UUID, audit: AuditEntry) -> None:
    """Guarda un registro de la bitácora sobre un caso, en la transacción abierta.

    Args:
        conn: Conexión con la transacción del cambio.
        case_id: Caso.
        audit: Quién, qué y con qué datos.
    """
    await conn.execute(
        text(
            "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
            "VALUES (:user_id, :action, :entity_type, :entity_id, "
            "CAST(:payload AS jsonb), CAST(:ip AS inet))"
        ),
        {
            "user_id": audit.actor.user_id,
            "action": audit.action,
            "entity_type": ENTITY_TYPE,
            "entity_id": str(case_id),
            "payload": json.dumps(dict(audit.payload), ensure_ascii=False, default=str),
            "ip": audit.actor.ip,
        },
    )


async def touch(conn: AsyncConnection, case_id: UUID) -> None:
    """Marca que el caso cambió ahora (lo sube en la lista de casos).

    Args:
        conn: Conexión con la transacción del cambio.
        case_id: Caso.
    """
    await conn.execute(text("UPDATE cases SET updated_at = now() WHERE id = :id"), {"id": case_id})


class PostgresCaseRepository:
    """Lectura y escritura de casos con su bitácora."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido de la aplicación.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def _one_case(self, conn: AsyncConnection, case_id: UUID) -> Case:
        row = (
            (
                await conn.execute(
                    text(f"SELECT {_COLUMNS} FROM cases c WHERE c.id = :id"),  # noqa: S608 — columnas fijas del módulo
                    {"id": case_id},
                )
            )
            .mappings()
            .one()
        )
        return _to_case(row)

    async def create(self, data: CaseDraft, created_by: str, audit: AuditEntry) -> Case:
        """Ver ``CaseRepositoryPort.create``."""
        async with self._engine.begin() as conn:
            case_id = (
                await conn.execute(
                    text(
                        "INSERT INTO cases (name, name_norm, description, sensitivity, "
                        "created_by) VALUES (:name, :name_norm, :description, :sensitivity, "
                        ":created_by) RETURNING id"
                    ),
                    {
                        "name": data.name,
                        "name_norm": data.name_norm,
                        "description": data.description or None,
                        "sensitivity": data.sensitivity.value,
                        "created_by": created_by,
                    },
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO case_members (case_id, user_id, role, added_by) "
                    "VALUES (:id, :user, :role, :user)"
                ),
                {"id": case_id, "user": created_by, "role": CaseMemberRole.OWNER.value},
            )
            await write_audit(conn, case_id, audit)
            return await self._one_case(conn, case_id)

    async def get_view(
        self, case_id: UUID, user_id: str, *, include_deleted: bool = False
    ) -> CaseView | None:
        """Ver ``CaseRepositoryPort.get_view``."""
        live = "" if include_deleted else "AND c.deleted_at IS NULL"
        sql = f"""
            SELECT {_COLUMNS}, m.role
            FROM cases c
            JOIN case_members m ON m.case_id = c.id AND m.user_id = :user
            WHERE c.id = :id {live}
        """  # noqa: S608 — columnas y condición fijas del módulo
        async with self._engine.connect() as conn:
            row = (
                (await conn.execute(text(sql), {"id": case_id, "user": user_id})).mappings().first()
            )
        return _to_view(row) if row else None

    async def list_for_user(
        self,
        user_id: str,
        statuses: Sequence[CaseStatus],
        contains_article: int | None,
        after: TimeCursor | None,
        limit: int,
    ) -> list[CaseView]:
        """Ver ``CaseRepositoryPort.list_for_user``."""
        params: dict[str, Any] = {
            "user": user_id,
            "statuses": [s.value for s in statuses],
            "article": contains_article,
            "limit": limit,
        }
        page = ""
        if after is not None and after.moment is not None:
            page = "AND (c.updated_at, c.id) < (:after_moment, CAST(:after_id AS uuid))"
            params.update({"after_moment": after.moment, "after_id": after.id})
        has_article = (
            "EXISTS (SELECT 1 FROM case_articles ca WHERE ca.case_id = c.id "
            "AND ca.article_id = :article)"
            if contains_article is not None
            else "NULL::boolean"
        )
        sql = f"""
            SELECT {_COLUMNS}, m.role, {has_article} AS has_article
            FROM case_members m
            JOIN cases c ON c.id = m.case_id
            WHERE m.user_id = :user AND c.status = ANY(:statuses) AND c.deleted_at IS NULL
                {page}
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT :limit
        """  # noqa: S608 — columnas y condiciones son texto fijo de este módulo
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(sql), params)).mappings().all()
        return [_to_view(row) for row in rows]

    async def set_deleted(
        self, case_id: UUID, *, deleted: bool, user_id: str, audit: AuditEntry
    ) -> None:
        """Ver ``CaseRepositoryPort.set_deleted``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE cases SET deleted_at = CASE WHEN :deleted THEN now() END, "
                    "deleted_by = CASE WHEN :deleted THEN :user END WHERE id = :id"
                ),
                {"id": case_id, "deleted": deleted, "user": user_id},
            )
            await write_audit(conn, case_id, audit)

    async def update(
        self,
        case_id: UUID,
        *,
        data: CaseDraft,
        status: CaseStatus,
        closed_at: datetime | None,
        audit: AuditEntry,
    ) -> Case:
        """Ver ``CaseRepositoryPort.update``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE cases SET name = :name, name_norm = :name_norm, "
                    "description = :description, sensitivity = :sensitivity, "
                    "status = :status, closed_at = :closed_at, updated_at = now() "
                    "WHERE id = :id"
                ),
                {
                    "id": case_id,
                    "name": data.name,
                    "name_norm": data.name_norm,
                    "description": data.description or None,
                    "sensitivity": data.sensitivity.value,
                    "status": status.value,
                    "closed_at": closed_at,
                },
            )
            await write_audit(conn, case_id, audit)
            return await self._one_case(conn, case_id)

    async def record_view(self, case_id: UUID, audit: AuditEntry, window_minutes: int) -> bool:
        """Ver ``CaseRepositoryPort.record_view``."""
        params: Mapping[str, Any] = {
            "user_id": audit.actor.user_id,
            "action": audit.action,
            "entity_type": ENTITY_TYPE,
            "entity_id": str(case_id),
            "payload": json.dumps(dict(audit.payload), ensure_ascii=False),
            "ip": audit.actor.ip,
            "minutes": window_minutes,
        }
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
                    "SELECT :user_id, :action, :entity_type, :entity_id, "
                    "CAST(:payload AS jsonb), CAST(:ip AS inet) "
                    "WHERE NOT EXISTS (SELECT 1 FROM audit_log "
                    "WHERE entity_type = :entity_type AND entity_id = :entity_id "
                    "AND action = :action AND user_id = :user_id "
                    "AND created_at > now() - make_interval(mins => :minutes))"
                ),
                dict(params),
            )
        return bool(result.rowcount)

    async def article_exists(self, article_id: int) -> bool:
        """Ver ``CaseRepositoryPort.article_exists``."""
        async with self._engine.connect() as conn:
            found = await conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM articles WHERE id = :id)"), {"id": article_id}
            )
            return bool(found.scalar_one())

    async def add_article(
        self, case_id: UUID, article_id: int, added_by: str, audit: AuditEntry
    ) -> bool:
        """Ver ``CaseRepositoryPort.add_article``."""
        async with self._engine.begin() as conn:
            added = (
                await conn.execute(
                    text(
                        "INSERT INTO case_articles (case_id, article_id, added_by) "
                        "VALUES (:case, :article, :by) ON CONFLICT DO NOTHING RETURNING article_id"
                    ),
                    {"case": case_id, "article": article_id, "by": added_by},
                )
            ).first()
            if added is None:
                return False
            await write_audit(conn, case_id, audit)
            await touch(conn, case_id)
            return True

    async def remove_article(self, case_id: UUID, article_id: int, audit: AuditEntry) -> bool:
        """Ver ``CaseRepositoryPort.remove_article``."""
        async with self._engine.begin() as conn:
            removed = (
                await conn.execute(
                    text(
                        "DELETE FROM case_articles WHERE case_id = :case AND article_id = :article "
                        "RETURNING article_id"
                    ),
                    {"case": case_id, "article": article_id},
                )
            ).first()
            if removed is None:
                return False
            await write_audit(conn, case_id, audit)
            await touch(conn, case_id)
            return True

    async def list_articles(
        self, case_id: UUID, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        """Ver ``CaseRepositoryPort.list_articles``."""
        params: dict[str, Any] = {"case": case_id, "limit": limit}
        page = ""
        if after is not None:
            # Mismo orden que las notas de una búsqueda: las más recientes
            # primero, las que no tienen fecha al final, y en empate por id.
            if after.moment is None:
                page = "AND a.published_at IS NULL AND a.id < :after_id"
            else:
                page = (
                    "AND (a.published_at < :after_moment OR a.published_at IS NULL "
                    "OR (a.published_at = :after_moment AND a.id < :after_id))"
                )
                params["after_moment"] = after.moment
            params["after_id"] = int(after.id)
        sql = f"""
            SELECT {ARTICLE_COLUMNS}, NULL::boolean AS in_region,
                {ALL_PROVIDERS} AS providers, {PRIMARY_COLUMNS},
                {ALL_JUDGEMENTS} AS judgements
            FROM case_articles ca
            JOIN articles a ON a.id = ca.article_id
            LEFT JOIN article_locations p ON p.article_id = a.id AND p.is_primary
            LEFT JOIN regions r ON r.id = p.region_id
            WHERE ca.case_id = :case {page}
            ORDER BY a.published_at DESC NULLS LAST, a.id DESC
            LIMIT :limit
        """  # noqa: S608 — columnas y condiciones son texto fijo de article_rows y de este módulo
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(sql), params)).mappings().all()
        return [article_item(row) for row in rows]

    async def list_members(self, case_id: UUID) -> list[CaseMember]:
        """Ver ``CaseRepositoryPort.list_members``."""
        async with self._engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT user_id, role, added_by, created_at FROM case_members "
                            "WHERE case_id = :case ORDER BY role = 'owner' DESC, user_id"
                        ),
                        {"case": case_id},
                    )
                )
                .mappings()
                .all()
            )
        return [
            CaseMember(r["user_id"], CaseMemberRole(r["role"]), r["added_by"], r["created_at"])
            for r in rows
        ]

    async def save_member(self, case_id: UUID, member: CaseMember, audit: AuditEntry) -> bool:
        """Ver ``CaseRepositoryPort.save_member``.

        Nunca cambia el rol del dueño: el ``DO UPDATE`` lo excluye.
        """
        async with self._engine.begin() as conn:
            changed = (
                await conn.execute(
                    text(
                        "INSERT INTO case_members AS m (case_id, user_id, role, added_by) "
                        "VALUES (:case, :user, :role, :by) "
                        "ON CONFLICT (case_id, user_id) DO UPDATE SET role = EXCLUDED.role "
                        "WHERE m.role <> EXCLUDED.role AND m.role <> 'owner' "
                        "RETURNING user_id"
                    ),
                    {
                        "case": case_id,
                        "user": member.user_id,
                        "role": member.role.value,
                        "by": member.added_by,
                    },
                )
            ).first()
            if changed is None:
                return False
            await write_audit(conn, case_id, audit)
            return True

    async def remove_member(self, case_id: UUID, user_id: str, audit: AuditEntry) -> bool:
        """Ver ``CaseRepositoryPort.remove_member``. El dueño nunca se borra."""
        async with self._engine.begin() as conn:
            removed = (
                await conn.execute(
                    text(
                        "DELETE FROM case_members WHERE case_id = :case AND user_id = :user "
                        "AND role <> 'owner' RETURNING user_id"
                    ),
                    {"case": case_id, "user": user_id},
                )
            ).first()
            if removed is None:
                return False
            await write_audit(conn, case_id, audit)
            return True
