"""Clasificación por categoría en lotes (F12.4, ADR-0029), con IA y base en memoria."""

from collections.abc import Sequence

import pytest

from app.application.ports.llm import (
    ClassificationLabel,
    ClassificationNote,
    ClassificationRequest,
    ClassificationResult,
)
from app.application.use_cases.classify import ClassifyArticles
from app.domain.categories import Category, CategoryChoice
from app.domain.enrichment import LLMUsage

pytestmark = pytest.mark.anyio

ARMAS = Category(6, "Armas y explosivos", "Armas")
OTROS = Category(14, "Otros", "Lo demás", is_other=True)


class FakeStore:
    def __init__(self, notes: Sequence[ClassificationNote]) -> None:
        self.notes = {n.article_id: n for n in notes}
        self.versions: dict[int, str] = {}
        self.saved: list[tuple[list[CategoryChoice], str]] = []

    async def active_categories(self) -> list[Category]:
        return [ARMAS, OTROS]

    async def pending_notes(
        self, article_ids: Sequence[int], version: str
    ) -> list[ClassificationNote]:
        return [
            self.notes[i]
            for i in sorted(article_ids)
            if i in self.notes and self.versions.get(i) != version
        ]

    async def pending_after(
        self, after_id: int, limit: int, version: str
    ) -> list[ClassificationNote]:
        ids = [i for i in sorted(self.notes) if i > after_id and self.versions.get(i) != version]
        return [self.notes[i] for i in ids[:limit]]

    async def save(self, choices: Sequence[CategoryChoice], version: str) -> None:
        self.saved.append((list(choices), version))
        for c in choices:
            self.versions[c.article_id] = version


class FakeClassifier:
    """La IA: armas para lo que diga «armas», una categoría inventada para el resto."""

    model = "gpt-6-luna"
    classify_prompt_version = "classify_v1"

    def __init__(self, *, skip: int | None = None) -> None:
        self.batches: list[list[int]] = []
        self.skip = skip

    async def classify(self, request: ClassificationRequest) -> ClassificationResult:
        self.batches.append([n.article_id for n in request.notes])
        labels = tuple(
            ClassificationLabel(
                n.article_id,
                "Armas y explosivos" if "armas" in n.title else "Robo de autos",
                "tráfico de armas" if "armas" in n.title else "robo de autos",
            )
            for n in request.notes
            if n.article_id != self.skip
        )
        return ClassificationResult(labels, LLMUsage(100, 10), self.model, "classify_v1")


def notes(*titles: str) -> list[ClassificationNote]:
    return [ClassificationNote(i, t, None) for i, t in enumerate(titles, start=1)]


async def test_clasifica_por_lotes_y_lo_que_no_encaja_va_a_otros() -> None:
    store = FakeStore(notes("Aseguran armas", "Roban autos", "Más armas"))
    ai = FakeClassifier()

    report = await ClassifyArticles(store, ai, batch_size=2).run([1, 2, 3])

    assert ai.batches == [[1, 2], [3]]
    assert report.classified == 3
    assert report.usage == LLMUsage(200, 20)
    saved = {c.article_id: (c.category, c.raw_label) for batch, _ in store.saved for c in batch}
    assert saved == {
        1: (ARMAS, "tráfico de armas"),
        2: (OTROS, "robo de autos"),
        3: (ARMAS, "tráfico de armas"),
    }
    assert {version for _, version in store.saved} == {"classify_v1"}


async def test_lo_ya_clasificado_con_la_misma_version_no_se_vuelve_a_mandar() -> None:
    store = FakeStore(notes("Aseguran armas", "Roban autos"))
    store.versions[1] = "classify_v1"
    ai = FakeClassifier()

    await ClassifyArticles(store, ai).run([1, 2])

    assert ai.batches == [[2]]


async def test_lo_que_la_ia_no_respondio_queda_pendiente() -> None:
    store = FakeStore(notes("Aseguran armas", "Roban autos"))

    report = await ClassifyArticles(store, FakeClassifier(skip=2)).run([1, 2])

    assert report.classified == 1
    assert 2 not in store.versions


async def test_la_muestra_no_guarda() -> None:
    store = FakeStore(notes("Aseguran armas", "Roban autos", "Más armas"))

    report = await ClassifyArticles(store, FakeClassifier()).sample([2, 3], size=1)

    assert [c.article_id for c in report.choices] == [2]
    assert report.notes[2].title == "Roban autos"
    assert store.saved == []


async def test_todas_las_pendientes_por_cursor() -> None:
    store = FakeStore(notes(*(f"armas {i}" for i in range(5))))
    ai = FakeClassifier()

    report = await ClassifyArticles(store, ai, batch_size=2).run_pending()

    assert report.classified == 5
    assert ai.batches == [[1, 2], [3, 4], [5]]


async def test_sin_notas_no_llama_a_la_ia() -> None:
    ai = FakeClassifier()

    assert (await ClassifyArticles(FakeStore([]), ai).run([])).classified == 0
    assert ai.batches == []
