"""Repositorio de conceptos sobre PostgreSQL.

Implementa ``ConceptRepositoryPort`` con SQL explícito, como el de regiones,
para que las consultas se puedan copiar a DBeaver o ``psql`` tal cual.

- Solo ve conceptos vigentes (``deleted_at IS NULL``). Los de búsqueda rápida
  (``is_quick``, ADR-0110) no salen en la lista ni ocupan su nombre.
- Cada escritura y su registro en ``audit_log`` van en una sola transacción.
- La base es la última defensa del nombre único: si dos personas guardan el
  mismo nombre a la vez, el índice único parcial rechaza al segundo y aquí
  se traduce a ``ConceptNameTakenError``.

No hace: no valida reglas de negocio (eso es del dominio y los casos de uso).
"""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.application.audit import AuditEntry
from app.application.pagination import NameCursor
from app.domain.concept import Concept, ConceptDraft, QueryMode
from app.domain.errors import ConceptNameTakenError, ConceptNotFoundError

ENTITY_TYPE = "concept"
# Una propuesta de frases todavía no es un concepto: su registro va con el id 0.
SUGGESTION_ENTITY_ID = 0
# Nombre del índice único de la migración 0005: identifica el choque de nombres.
_NAME_UNIQUE_INDEX = "concepts_name_norm_active_key"
_COLUMNS = """
    c.id, c.name, c.description, c.keywords, c.exclude_terms, c.color, c.is_active,
    c.created_by, c.created_at, c.updated_at, c.category_id, c.query_mode, c.is_quick
"""


def _to_concept(row: RowMapping) -> Concept:
    # Los datos ya pasaron por ConceptDraft.validated al guardarse y la base
    # garantiza lo mínimo; no se vuelven a validar al leer.
    data = ConceptDraft(
        name=row["name"],
        description=row["description"],
        keywords=tuple(row["keywords"]),
        exclude_terms=tuple(row["exclude_terms"]),
        color=row["color"],
        is_active=row["is_active"],
        query_mode=QueryMode(row["query_mode"]),
    )
    return Concept(
        row["id"],
        data,
        row["created_by"],
        row["created_at"],
        row["updated_at"],
        row["category_id"],
        row["is_quick"],
    )


def _values(data: ConceptDraft) -> dict[str, Any]:
    return {
        "name": data.name,
        "name_norm": data.name_norm,
        "description": data.description,
        "keywords": list(data.keywords),
        "exclude_terms": list(data.exclude_terms),
        "color": data.color,
        "is_active": data.is_active,
        "query_mode": data.query_mode.value,
    }


def _is_name_clash(error: IntegrityError) -> bool:
    return _NAME_UNIQUE_INDEX in str(error.orig)


async def _write_audit(conn: AsyncConnection, concept_id: int, audit: AuditEntry) -> None:
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
            "entity_id": str(concept_id),
            "payload": json.dumps(dict(audit.payload), ensure_ascii=False),
            "ip": audit.actor.ip,
        },
    )


class PostgresConceptRepository:
    """Lectura y escritura de ``concepts`` con su bitácora."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido de la aplicación.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def _fetch(self, sql: str, params: Mapping[str, Any]) -> list[Concept]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(sql), dict(params))).mappings().all()
        return [_to_concept(row) for row in rows]

    async def list_concepts(
        self, active: bool | None, after: NameCursor | None, limit: int
    ) -> list[Concept]:
        """Ver ``ConceptRepositoryPort.list_concepts``."""
        return await self._fetch(
            f"""
            SELECT {_COLUMNS} FROM concepts c
            WHERE c.deleted_at IS NULL AND NOT c.is_quick
              AND (CAST(:active AS boolean) IS NULL OR c.is_active = :active)
              AND (CAST(:after_name AS text) IS NULL
                   OR (c.name_norm, c.id) > (:after_name, :after_id))
            ORDER BY c.name_norm, c.id
            LIMIT :limit
            """,  # noqa: S608 — fragmentos SQL constantes del módulo
            {
                "active": active,
                "after_name": after.name_norm if after else None,
                "after_id": after.id if after else 0,
                "limit": limit,
            },
        )

    async def get(self, concept_id: int) -> Concept | None:
        """Ver ``ConceptRepositoryPort.get``."""
        rows = await self._fetch(
            f"SELECT {_COLUMNS} FROM concepts c WHERE c.id = :id AND c.deleted_at IS NULL",  # noqa: S608 — fragmentos SQL constantes del módulo
            {"id": concept_id},
        )
        return rows[0] if rows else None

    async def for_category(self, category_id: int) -> Concept | None:
        """Ver ``ConceptRepositoryPort.for_category``."""
        rows = await self._fetch(
            f"SELECT {_COLUMNS} FROM concepts c "  # noqa: S608 — fragmentos SQL constantes del módulo
            "WHERE c.category_id = :category AND c.deleted_at IS NULL",
            {"category": category_id},
        )
        return rows[0] if rows else None

    async def name_taken(self, name_norm: str, except_id: int | None) -> bool:
        """Ver ``ConceptRepositoryPort.name_taken``."""
        async with self._engine.connect() as conn:
            taken = await conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM concepts WHERE name_norm = :n "
                    "AND deleted_at IS NULL AND NOT is_quick "
                    "AND id <> COALESCE(CAST(:except_id AS bigint), 0))"
                ),
                {"n": name_norm, "except_id": except_id},
            )
            return bool(taken.scalar_one())

    async def create(
        self, data: ConceptDraft, created_by: str, audit: AuditEntry, *, quick: bool = False
    ) -> Concept:
        """Ver ``ConceptRepositoryPort.create``."""
        try:
            async with self._engine.begin() as conn:
                row = (
                    (
                        await conn.execute(
                            text(
                                f"""
                                INSERT INTO concepts AS c (name, name_norm, description, keywords,
                                    exclude_terms, color, is_active, query_mode, created_by,
                                    is_quick)
                                VALUES (:name, :name_norm, :description, :keywords,
                                    :exclude_terms, :color, :is_active, :query_mode, :created_by,
                                    :is_quick)
                                RETURNING {_COLUMNS}
                                """  # noqa: S608 — fragmentos SQL constantes del módulo
                            ),
                            {**_values(data), "created_by": created_by, "is_quick": quick},
                        )
                    )
                    .mappings()
                    .one()
                )
                await _write_audit(conn, row["id"], audit)
        except IntegrityError as error:
            if _is_name_clash(error):
                raise ConceptNameTakenError(
                    f'Ya existe un concepto llamado "{data.name}".', {"name": data.name}
                ) from error
            raise
        return _to_concept(row)

    async def update(self, concept_id: int, data: ConceptDraft, audit: AuditEntry) -> Concept:
        """Ver ``ConceptRepositoryPort.update``."""
        try:
            async with self._engine.begin() as conn:
                row = (
                    (
                        await conn.execute(
                            text(
                                f"""
                                UPDATE concepts AS c SET name = :name, name_norm = :name_norm,
                                    description = :description, keywords = :keywords,
                                    exclude_terms = :exclude_terms, color = :color,
                                    is_active = :is_active, query_mode = :query_mode
                                WHERE c.id = :id AND c.deleted_at IS NULL
                                RETURNING {_COLUMNS}
                                """  # noqa: S608 — fragmentos SQL constantes del módulo
                            ),
                            {**_values(data), "id": concept_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ConceptNotFoundError("No existe ese concepto.", {"id": concept_id})
                await _write_audit(conn, concept_id, audit)
        except IntegrityError as error:
            if _is_name_clash(error):
                raise ConceptNameTakenError(
                    f'Ya existe un concepto llamado "{data.name}".', {"name": data.name}
                ) from error
            raise
        return _to_concept(row)

    async def keep(self, concept_id: int, audit: AuditEntry) -> Concept:
        """Ver ``ConceptRepositoryPort.keep``."""
        try:
            async with self._engine.begin() as conn:
                row = (
                    (
                        await conn.execute(
                            text(
                                f"""
                                UPDATE concepts AS c SET is_quick = false
                                WHERE c.id = :id AND c.is_quick AND c.deleted_at IS NULL
                                RETURNING {_COLUMNS}
                                """  # noqa: S608 — fragmentos SQL constantes del módulo
                            ),
                            {"id": concept_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ConceptNotFoundError(
                        "No hay una búsqueda rápida con ese id.", {"id": concept_id}
                    )
                await _write_audit(conn, concept_id, audit)
        except IntegrityError as error:
            if _is_name_clash(error):
                raise ConceptNameTakenError(
                    "Ya existe un concepto con ese nombre.", {"id": concept_id}
                ) from error
            raise
        return _to_concept(row)

    async def delete(self, concept_id: int, *, logical: bool, audit: AuditEntry) -> None:
        """Ver ``ConceptRepositoryPort.delete``."""
        sql = (
            "UPDATE concepts SET deleted_at = now() WHERE id = :id AND deleted_at IS NULL"
            if logical
            else "DELETE FROM concepts WHERE id = :id AND deleted_at IS NULL"
        )
        async with self._engine.begin() as conn:
            result = await conn.execute(text(sql), {"id": concept_id})
            if result.rowcount == 0:
                raise ConceptNotFoundError("No existe ese concepto.", {"id": concept_id})
            await _write_audit(conn, concept_id, audit)

    async def is_used_in_searches(self, concept_id: int) -> bool:
        """Ver ``ConceptRepositoryPort.is_used_in_searches``.

        Un concepto con búsquedas no se puede borrar físicamente: su copia en
        ``search_concepts`` y sus juicios en ``article_concepts`` lo apuntan.
        """
        async with self._engine.connect() as conn:
            used = (
                await conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM search_concepts WHERE concept_id = :id) "
                        "OR EXISTS (SELECT 1 FROM article_concepts WHERE concept_id = :id)"
                    ),
                    {"id": concept_id},
                )
            ).scalar_one()
        return bool(used)

    async def record_suggestion(self, audit: AuditEntry) -> None:
        """Ver ``ConceptRepositoryPort.record_suggestion``."""
        async with self._engine.begin() as conn:
            await _write_audit(conn, SUGGESTION_ENTITY_ID, audit)
