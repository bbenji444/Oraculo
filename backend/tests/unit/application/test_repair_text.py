"""Caso de uso de reparación de Mojibake en las notas guardadas (F12.1)."""

from collections.abc import Sequence

import pytest

from app.application.ports.text_repair import StoredRow, TextTable
from app.application.use_cases.repair_text import RepairStoredText

pytestmark = pytest.mark.anyio


class FakeStore:
    """Tabla en memoria con lectura por cursor."""

    def __init__(self, rows: Sequence[StoredRow]) -> None:
        self.rows = {r.row_id: r for r in rows}
        self.saved: list[list[StoredRow]] = []
        self.fetches = 0

    async def fetch(self, table: TextTable, after_id: int, limit: int) -> Sequence[StoredRow]:
        self.fetches += 1
        return [self.rows[k] for k in sorted(self.rows) if k > after_id][:limit]

    async def save(self, table: TextTable, rows: Sequence[StoredRow]) -> None:
        self.saved.append(list(rows))
        for row in rows:
            self.rows[row.row_id] = row


def _rows() -> list[StoredRow]:
    return [
        StoredRow(1, {"title": "Maru seÃ±alÃ³ corrupciÃ³n", "snippet": None}),
        StoredRow(2, {"title": "Peñón de los Baños", "snippet": "sin cambios"}),
        StoredRow(3, {"title": "Bien", "snippet": "JÃ¡uregui en ChihuahuaðŸŽ¦"}),
        StoredRow(5, {"title": "Todo bien", "snippet": None}),
    ]


async def test_sin_aplicar_cuenta_y_junta_ejemplos_pero_no_escribe() -> None:
    store = FakeStore(_rows())

    report = await RepairStoredText(store, batch_size=2).run("news_index", apply=False)

    assert (report.scanned, report.changed, report.applied) == (4, 2, False)
    assert store.saved == []
    assert [(e.row_id, e.column, e.after) for e in report.examples] == [
        (1, "title", "Maru señaló corrupción"),
        (3, "snippet", "Jáuregui en Chihuahua🎦"),
    ]


async def test_aplicando_guarda_solo_los_que_cambian_por_lote() -> None:
    store = FakeStore(_rows())

    report = await RepairStoredText(store, batch_size=2).run("articles", apply=True)

    assert report.changed == 2
    # Lote 1 (ids 1 y 2) guarda el 1; lote 2 (ids 3 y 5) guarda el 3.
    assert [[r.row_id for r in batch] for batch in store.saved] == [[1], [3]]
    assert store.rows[1].fields["title"] == "Maru señaló corrupción"
    assert store.rows[3].fields == {"title": "Bien", "snippet": "Jáuregui en Chihuahua🎦"}
    # Dos lotes llenos y una lectura vacía que termina el recorrido.
    assert store.fetches == 3


async def test_segunda_pasada_ya_no_encuentra_nada() -> None:
    store = FakeStore(_rows())
    use_case = RepairStoredText(store)

    await use_case.run("articles", apply=True)
    again = await use_case.run("articles", apply=True)

    assert again.changed == 0


async def test_limita_los_ejemplos() -> None:
    rows = [StoredRow(i, {"title": f"nota {i} con acciÃ³n"}) for i in range(1, 9)]

    report = await RepairStoredText(FakeStore(rows), sample_size=3).run("news_index", apply=False)

    assert report.changed == 8
    assert len(report.examples) == 3


async def test_tabla_vacia() -> None:
    report = await RepairStoredText(FakeStore([])).run("article_texts", apply=True)

    assert (report.scanned, report.changed) == (0, 0)
