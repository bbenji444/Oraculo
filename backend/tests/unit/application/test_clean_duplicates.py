"""Caso de uso de limpieza del índice local (F12.1b)."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from app.application.use_cases.clean_duplicates import CleanIndexDuplicates
from app.domain.dedupe import canonical_url, url_hash
from app.domain.index_cleanup import IndexKey

pytestmark = pytest.mark.anyio

NOON = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)


def key(note_id: int, url: str, title: str = "Huracán Trudy") -> IndexKey:
    return IndexKey(
        note_id=note_id,
        url=url,
        url_hash=f"cruda-{note_id}",
        title=title,
        source_domain=canonical_url(url).split("/")[2],
        text_norm=title.upper(),
        published_at=NOON,
        has_body=False,
    )


class FakeIndex:
    def __init__(self, keys: Sequence[IndexKey]) -> None:
        self.keys = {k.note_id: k for k in keys}
        self.deleted: list[list[int]] = []
        self.rehashed: list[list[tuple[int, str]]] = []

    async def fetch_keys(self, after_id: int, limit: int) -> Sequence[IndexKey]:
        return [self.keys[i] for i in sorted(self.keys) if i > after_id][:limit]

    async def delete(self, note_ids: Sequence[int]) -> int:
        self.deleted.append(list(note_ids))
        for i in note_ids:
            del self.keys[i]
        return len(note_ids)

    async def rehash(self, pairs: Sequence[tuple[int, str]]) -> None:
        self.rehashed.append(list(pairs))


def _keys() -> list[IndexKey]:
    return [
        key(1, "https://www.razon.com.mx/trudy"),
        key(2, "https://razon.com.mx:443/trudy"),
        key(3, "https://tiempo.com.mx/local/x", "🎦"),
        key(4, "https://milenio.com/otra", "Otra nota"),
    ]


async def test_sin_aplicar_cuenta_pero_no_escribe() -> None:
    index = FakeIndex(_keys())

    report = await CleanIndexDuplicates(index, batch_size=2).run(apply=False)

    assert (report.scanned, report.removed, report.rehashed) == (4, 2, 2)
    assert dict(report.by_reason) == {"misma_url": 1, "sin_letras": 1}
    # Un ejemplo de cada motivo primero.
    assert {e.reason for e in report.examples} == {"misma_url", "sin_letras"}
    assert index.deleted == []
    assert index.rehashed == []


async def test_aplicando_borra_y_luego_recalcula_por_lotes() -> None:
    index = FakeIndex(_keys())

    report = await CleanIndexDuplicates(index, batch_size=1).run(apply=True)

    assert report.removed == 2
    assert index.deleted == [[2], [3]]
    assert index.rehashed == [
        [(1, url_hash("https://razon.com.mx/trudy"))],
        [(4, url_hash("https://milenio.com/otra"))],
    ]
    assert sorted(index.keys) == [1, 4]


async def test_limita_los_ejemplos() -> None:
    keys = [key(i, f"https://medio.mx/{i}", "🎦") for i in range(1, 10)]

    report = await CleanIndexDuplicates(FakeIndex(keys), sample_size=3).run(apply=False)

    assert report.removed == 9
    assert len(report.examples) == 3
