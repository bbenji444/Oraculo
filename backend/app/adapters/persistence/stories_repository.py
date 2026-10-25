"""Historias sobre PostgreSQL: lectura por fecha y guardado de ``story_id`` (F12.1c).

Implementa ``StoryStorePort``. La ventana usa el índice
``articles_published_id`` y la lectura completa, cursor por id (nunca
``OFFSET``, CLAUDE.md §6.3). El lugar principal sale de
``article_locations.is_primary``.

No hace: no decide qué notas van juntas.
"""

from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.ports.stories import StoryWindow
from app.domain.stories import StoryNote

_SELECT = """
    SELECT a.id, a.title, a.source_name, a.source_domain, a.published_at, a.story_id,
        r.code AS place_code
    FROM articles a
    LEFT JOIN article_locations p ON p.article_id = a.id AND p.is_primary
    LEFT JOIN regions r ON r.id = p.region_id
"""


def _note(row: Row[Any]) -> StoryNote:
    return StoryNote(
        article_id=row.id,
        title=row.title,
        source_name=row.source_name,
        source_domain=row.source_domain,
        published_at=row.published_at,
        place_code=row.place_code,
        story_id=row.story_id,
    )


class PostgresStoryStore:
    """``StoryStorePort`` sobre ``articles``.

    Args:
        engine: Engine asíncrono de SQLAlchemy.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def window(self, article_ids: Sequence[int], span: timedelta) -> StoryWindow:
        """Ver ``StoryStorePort.window``."""
        async with self._engine.connect() as conn:
            targets = [
                _note(r)
                for r in await conn.execute(
                    text(f"{_SELECT} WHERE a.id = ANY(:ids) AND a.published_at IS NOT NULL"),
                    {"ids": list(article_ids)},
                )
            ]
            if not targets:
                return StoryWindow((), ())
            first = min(n.published_at for n in targets) - span
            last = max(n.published_at for n in targets) + span
            neighbors = [
                _note(r)
                for r in await conn.execute(
                    text(
                        f"{_SELECT} WHERE a.published_at BETWEEN :first AND :last "
                        "AND NOT (a.id = ANY(:ids))"
                    ),
                    {"first": first, "last": last, "ids": list(article_ids)},
                )
            ]
        return StoryWindow(tuple(targets), tuple(neighbors))

    async def fetch_all(self, after_id: int, limit: int) -> Sequence[StoryNote]:
        """Ver ``StoryStorePort.fetch_all``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    f"{_SELECT} WHERE a.id > :after AND a.published_at IS NOT NULL "
                    "ORDER BY a.id LIMIT :limit"
                ),
                {"after": after_id, "limit": limit},
            )
            return [_note(r) for r in rows]

    async def save(self, stories: Mapping[int, int | None]) -> None:
        """Ver ``StoryStorePort.save``."""
        if not stories:
            return
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE articles a SET story_id = v.story_id
                    FROM unnest(CAST(:ids AS bigint[]), CAST(:stories AS bigint[]))
                        AS v(id, story_id)
                    WHERE a.id = v.id
                    """
                ),
                {"ids": list(stories), "stories": list(stories.values())},
            )
