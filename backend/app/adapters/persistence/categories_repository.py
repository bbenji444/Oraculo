"""Catálogo de categorías y categoría de cada nota sobre PostgreSQL (F12.4, ADR-0029).

Implementa ``CategoryStorePort``. Al guardar la categoría guarda también
quién actúa en la nota (``articles.authority``, F12.5, ADR-0030).

Las notas pendientes son las que no tienen categoría de la versión vigente
del prompt (``category_version``). Se leen
por cursor (``WHERE id > :after ORDER BY id``, nunca ``OFFSET``) y se manda a
la IA solo título y resumen (o el fragmento del medio si no hay resumen).

No hace: no decide la categoría.
"""

import json
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.audit import AuditEntry
from app.application.ports.llm import ClassificationNote
from app.domain.categories import Category, CategoryChoice
from app.domain.concept import ConceptDraft
from app.domain.errors import CategoryNameTakenError, CategoryNotFoundError
from app.domain.names import normalize_name

# Entidad de la bitácora para las ediciones del catálogo (02/11/2026).
ENTITY_TYPE = "category"
_CATALOG = """
    SELECT c.id, c.name, c.description, c.is_other, c.color, c.symbol, c.is_active,
        (SELECT k.id FROM concepts k
         WHERE k.category_id = c.id AND k.deleted_at IS NULL) AS topic_concept_id
    FROM categories c
"""


def _to_category(row: Row) -> Category:
    return Category(
        row.id,
        row.name,
        row.description,
        row.is_other,
        row.color,
        row.symbol,
        row.is_active,
        row.topic_concept_id,
    )


_PENDING = """
    SELECT a.id, a.title, COALESCE(a.summary, a.snippet) AS summary,
        (SELECT string_agg(ac.relevance_reason, ' ' ORDER BY ac.concept_id)
         FROM article_concepts ac WHERE ac.article_id = a.id) AS reading_notes
    FROM articles a
    WHERE a.category_version IS DISTINCT FROM :version
"""


_AUDIT = text(
    "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
    "VALUES (:user_id, :action, :entity_type, :entity_id, CAST(:payload AS jsonb), "
    "CAST(:ip AS inet))"
)
# Una subdivisión nueva va antes de «Otros», que siempre queda al final.
_INSERT_CATEGORY = text(
    "INSERT INTO categories (name, name_norm, description, color, sort_order, is_active) "
    "VALUES (:name, :norm, :description, :color, "
    "(SELECT COALESCE(max(sort_order), 0) + 1 FROM categories WHERE NOT is_other), :active) "
    "RETURNING id, sort_order"
)
_INSERT_TOPIC = text(
    "INSERT INTO concepts (name, name_norm, description, keywords, exclude_terms, color, "
    "is_active, created_by, category_id) VALUES (:name, :name_norm, :description, "
    ":keywords, :exclude_terms, :color, :is_active, :created_by, :category_id)"
)


def _audit_params(audit: AuditEntry, entity_id: int) -> dict[str, object]:
    return {
        "user_id": audit.actor.user_id,
        "action": audit.action,
        "entity_type": ENTITY_TYPE,
        "entity_id": str(entity_id),
        "payload": json.dumps(dict(audit.payload), ensure_ascii=False),
        "ip": audit.actor.ip,
    }


class PostgresCategoryStore:
    """``CategoryStorePort`` sobre ``categories`` y ``articles``.

    Args:
        engine: Engine asíncrono de SQLAlchemy.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def active_categories(self) -> list[Category]:
        """Ver ``CategoryStorePort.active_categories``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(_CATALOG + " WHERE c.is_active ORDER BY c.sort_order, c.id")
            )
            return [_to_category(r) for r in rows]

    async def all_categories(self) -> list[Category]:
        """Ver ``CategoryStorePort.all_categories``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(text(_CATALOG + " ORDER BY c.sort_order, c.id"))
            return [_to_category(r) for r in rows]

    async def get_category(self, category_id: int) -> Category | None:
        """Ver ``CategoryStorePort.get_category``."""
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(text(_CATALOG + " WHERE c.id = :id"), {"id": category_id})
            ).first()
        return _to_category(row) if row else None

    async def update_category(self, category: Category, audit: AuditEntry) -> Category:
        """Ver ``CategoryStorePort.update_category``."""
        name_norm = normalize_name(category.name)
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE categories SET name = :name, name_norm = :norm, "
                        "description = :description, color = :color, is_active = :active, "
                        "updated_at = now() WHERE id = :id"
                    ),
                    {
                        "id": category.category_id,
                        "name": category.name,
                        "norm": name_norm,
                        "description": category.description,
                        "color": category.color,
                        "active": category.is_active,
                    },
                )
                # Su tema general se llama igual y se prende o apaga con ella.
                await conn.execute(
                    text(
                        "UPDATE concepts SET name = :name, name_norm = :norm, "
                        "is_active = :active WHERE category_id = :id AND deleted_at IS NULL"
                    ),
                    {
                        "id": category.category_id,
                        "name": category.name,
                        "norm": name_norm,
                        "active": category.is_active,
                    },
                )
                await conn.execute(
                    text(
                        "INSERT INTO audit_log "
                        "(user_id, action, entity_type, entity_id, payload, ip) "
                        "VALUES (:user_id, :action, :entity_type, :entity_id, "
                        "CAST(:payload AS jsonb), CAST(:ip AS inet))"
                    ),
                    {
                        "user_id": audit.actor.user_id,
                        "action": audit.action,
                        "entity_type": ENTITY_TYPE,
                        "entity_id": str(category.category_id),
                        "payload": json.dumps(dict(audit.payload), ensure_ascii=False),
                        "ip": audit.actor.ip,
                    },
                )
        except IntegrityError as error:
            raise CategoryNameTakenError(
                f'Ya existe una subdivisión o un concepto llamado "{category.name}".',
                {"name": category.name},
            ) from error
        saved = await self.get_category(category.category_id)
        if saved is None:
            raise CategoryNotFoundError(
                "La subdivisión ya no existe.", {"id": category.category_id}
            )
        return saved

    async def create_category(
        self, category: Category, topic: ConceptDraft, actor_id: str, audit: AuditEntry
    ) -> Category:
        """Ver ``CategoryCatalogPort.create_category``."""
        try:
            async with self._engine.begin() as conn:
                row = (
                    await conn.execute(
                        _INSERT_CATEGORY,
                        {
                            "name": category.name,
                            "norm": normalize_name(category.name),
                            "description": category.description,
                            "color": category.color,
                            "active": category.is_active,
                        },
                    )
                ).one()
                await conn.execute(
                    text(
                        "UPDATE categories SET sort_order = :after "
                        "WHERE is_other AND sort_order <= :order"
                    ),
                    {"order": row.sort_order, "after": row.sort_order + 1},
                )
                await conn.execute(
                    _INSERT_TOPIC,
                    {
                        "name": topic.name,
                        "name_norm": topic.name_norm,
                        "description": topic.description,
                        "keywords": list(topic.keywords),
                        "exclude_terms": list(topic.exclude_terms),
                        "color": topic.color,
                        "is_active": topic.is_active,
                        "created_by": actor_id,
                        "category_id": row.id,
                    },
                )
                await conn.execute(_AUDIT, _audit_params(audit, row.id))
        except IntegrityError as error:
            raise CategoryNameTakenError(
                f'Ya existe una subdivisión o un concepto llamado "{category.name}".',
                {"name": category.name},
            ) from error
        saved = await self.get_category(row.id)
        if saved is None:
            raise CategoryNotFoundError("La subdivisión ya no existe.", {"id": row.id})
        return saved

    async def delete_category(self, category: Category, audit: AuditEntry) -> int:
        """Ver ``CategoryCatalogPort.delete_category``."""
        async with self._engine.begin() as conn:
            moved = (
                await conn.execute(
                    text(
                        "UPDATE articles SET category_id = "
                        "(SELECT id FROM categories WHERE is_other) WHERE category_id = :id"
                    ),
                    {"id": category.category_id},
                )
            ).rowcount
            # El tema general se retira de forma lógica: las búsquedas pasadas
            # conservan su nombre (search_concepts.concept_name).
            await conn.execute(
                text(
                    "UPDATE concepts SET deleted_at = now(), is_active = false, "
                    "category_id = NULL WHERE category_id = :id AND deleted_at IS NULL"
                ),
                {"id": category.category_id},
            )
            await conn.execute(
                text("DELETE FROM categories WHERE id = :id AND NOT is_other"),
                {"id": category.category_id},
            )
            payload = {**dict(audit.payload), "notes_moved_to_other": moved}
            await conn.execute(
                _AUDIT,
                _audit_params(AuditEntry(audit.actor, audit.action, payload), category.category_id),
            )
        return int(moved or 0)

    async def pending_notes(
        self, article_ids: Sequence[int], version: str
    ) -> list[ClassificationNote]:
        """Ver ``CategoryStorePort.pending_notes``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(f"{_PENDING} AND a.id = ANY(:ids) ORDER BY a.id"),
                {"version": version, "ids": list(article_ids)},
            )
            return [ClassificationNote(r.id, r.title, r.summary, r.reading_notes) for r in rows]

    async def pending_after(
        self, after_id: int, limit: int, version: str
    ) -> list[ClassificationNote]:
        """Ver ``CategoryStorePort.pending_after``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(f"{_PENDING} AND a.id > :after ORDER BY a.id LIMIT :limit"),
                {"version": version, "after": after_id, "limit": limit},
            )
            return [ClassificationNote(r.id, r.title, r.summary, r.reading_notes) for r in rows]

    async def save(self, choices: Sequence[CategoryChoice], version: str) -> None:
        """Ver ``CategoryStorePort.save``."""
        if not choices:
            return
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE articles a SET category_id = v.category_id, category_raw = v.raw,
                        authority = v.authority, category_version = :version,
                        updated_at = now()
                    FROM unnest(CAST(:ids AS bigint[]), CAST(:categories AS bigint[]),
                        CAST(:raws AS text[]), CAST(:authorities AS text[]))
                        AS v(id, category_id, raw, authority)
                    WHERE a.id = v.id
                    """
                ),
                {
                    "ids": [c.article_id for c in choices],
                    "categories": [c.category.category_id for c in choices],
                    "raws": [c.raw_label for c in choices],
                    "authorities": [c.authority.value if c.authority else None for c in choices],
                    "version": version,
                },
            )

    async def search_article_ids(self, search_id: UUID) -> list[int]:
        """Notas que encontró una búsqueda (para tomar ejemplos de ``make clasificar``).

        Args:
            search_id: Búsqueda.

        Returns:
            Los ids de sus notas, en orden.
        """
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT DISTINCT article_id FROM search_results WHERE search_id = :id "
                    "ORDER BY article_id"
                ),
                {"id": search_id},
            )
            return [int(r.article_id) for r in rows]

    async def count_pending(self, version: str) -> int:
        """Cuántas notas faltan por clasificar con esta versión (para ``make clasificar``).

        Args:
            version: Versión vigente del prompt de clasificación.

        Returns:
            El número de notas pendientes.
        """
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT count(*) FROM articles WHERE category_version IS DISTINCT FROM :version"
                ),
                {"version": version},
            )
            return int(result.scalar_one())
