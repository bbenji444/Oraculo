"""Catálogo de categorías y categoría de cada nota sobre PostgreSQL (F12.4, ADR-0029).

Implementa ``CategoryStorePort``. Al guardar la categoría guarda también
quién actúa en la nota (``articles.authority``, F12.5, ADR-0030).

Las notas pendientes son las que no tienen categoría de la versión vigente
del prompt (``category_version``). Se leen
por cursor (``WHERE id > :after ORDER BY id``, nunca ``OFFSET``) y se manda a
la IA solo título y resumen (o el fragmento del medio si no hay resumen).

No hace: no decide la categoría.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.ports.llm import ClassificationNote
from app.domain.categories import Category, CategoryChoice

_PENDING = """
    SELECT a.id, a.title, COALESCE(a.summary, a.snippet) AS summary,
        (SELECT string_agg(ac.relevance_reason, ' ' ORDER BY ac.concept_id)
         FROM article_concepts ac WHERE ac.article_id = a.id) AS reading_notes
    FROM articles a
    WHERE a.category_version IS DISTINCT FROM :version
"""


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
                text(
                    "SELECT id, name, description, is_other, color, symbol FROM categories "
                    "WHERE is_active ORDER BY sort_order, id"
                )
            )
            return [
                Category(r.id, r.name, r.description, r.is_other, r.color, r.symbol) for r in rows
            ]

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
