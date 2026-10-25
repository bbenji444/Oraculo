"""Casos de uso de historias (F12.1c)."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.text.similarity import title_similarity, title_token_similarity
from app.application.ports.stories import StoryWindow
from app.application.use_cases.stories import GroupStories, RegroupAllStories
from app.domain.stories import StoryNote

pytestmark = pytest.mark.anyio

T0 = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)
BALACERA = "Balacera en Iztapalapa deja dos muertos y un herido"


def note(article_id: int, title: str, hours: float = 0, story_id: int | None = None) -> StoryNote:
    return StoryNote(article_id, title, None, None, T0 + timedelta(hours=hours), "09007", story_id)


class FakeStore:
    def __init__(self, notes: Sequence[StoryNote]) -> None:
        self.notes = {n.article_id: n for n in notes}
        self.saved: list[dict[int, int | None]] = []

    async def window(self, article_ids: Sequence[int], span: timedelta) -> StoryWindow:
        targets = tuple(self.notes[i] for i in article_ids if i in self.notes)
        first = min(n.published_at for n in targets) - span
        last = max(n.published_at for n in targets) + span
        neighbors = tuple(
            n
            for n in self.notes.values()
            if n.article_id not in article_ids and first <= n.published_at <= last
        )
        return StoryWindow(targets, neighbors)

    async def fetch_all(self, after_id: int, limit: int) -> Sequence[StoryNote]:
        return [self.notes[i] for i in sorted(self.notes) if i > after_id][:limit]

    async def save(self, stories: Mapping[int, int | None]) -> None:
        self.saved.append(dict(stories))
        for article_id, story_id in stories.items():
            self.notes[article_id] = replace(self.notes[article_id], story_id=story_id)


async def test_agrupa_las_notas_de_la_busqueda_con_sus_vecinas() -> None:
    store = FakeStore(
        [
            note(1, BALACERA, 0),
            note(2, f"{BALACERA} en Ermita", 5),
            note(3, "Receta de pollo con salsa de cempasúchil", 6),
        ]
    )

    changed = await GroupStories(store, title_similarity, title_token_similarity).run([2, 3])

    assert changed == 2
    assert store.saved == [{1: 1, 2: 1}]


async def test_sin_notas_no_consulta() -> None:
    store = FakeStore([])

    assert await GroupStories(store, title_similarity, title_token_similarity).run([]) == 0


async def test_recalcular_todo_sin_aplicar_cuenta_y_no_escribe() -> None:
    store = FakeStore(
        [
            note(1, BALACERA, 0),
            note(2, f"{BALACERA} en Ermita", 5),
            note(3, f"{BALACERA}; hay dos detenidos", 8),
            note(4, "Receta de pollo con salsa de cempasúchil", 6),
            # Estaba en una historia equivocada: al recalcular queda sola.
            note(5, "Karol G suma cuatro triunfos en los Billboard", 7, story_id=1),
        ]
    )

    report = await RegroupAllStories(store, title_similarity, title_token_similarity).run(
        apply=False
    )

    assert (report.scanned, report.stories, report.grouped, report.changed) == (5, 1, 3, 4)
    assert [n.article_id for n in report.examples[0]] == [1, 2, 3]
    assert store.saved == []


async def test_recalcular_todo_aplicando_guarda_y_deja_solas_a_las_que_sobran() -> None:
    store = FakeStore(
        [
            note(1, BALACERA, 0),
            note(2, f"{BALACERA} en Ermita", 5),
            note(5, "Karol G suma cuatro triunfos en los Billboard", 7, story_id=1),
        ]
    )
    use_case = RegroupAllStories(store, title_similarity, title_token_similarity, batch_size=1)

    await use_case.run(apply=True)
    again = await use_case.run(apply=True)

    assert {i: n.story_id for i, n in store.notes.items()} == {1: 1, 2: 1, 5: None}
    assert again.changed == 0
