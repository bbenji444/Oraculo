"""Reparar el Mojibake de las notas que ya están guardadas (F12.1).

Desde F12.1, las notas nuevas entran limpias (``RawArticle.create`` y
``NewsItem.create`` reparan el texto). Este caso de uso arregla las que
entraron antes: recorre cada tabla por lotes con cursor (CLAUDE.md §6.3),
repara cada texto con ``repair_mojibake`` y, solo si se le pide, guarda los
que cambiaron con un commit por lote.

Sin ``apply`` no escribe nada: sirve para ver cuántos renglones cambiarían
y ejemplos reales antes de aplicar (CLAUDE.md §2.6). Lo usa
``make reparar-texto``.

No hace: no decide qué columnas normalizadas recalcular (eso es del
adaptador) ni pide confirmación (eso es del comando).
"""

import logging
from dataclasses import dataclass, field

from app.application.ports.text_repair import StoredRow, StoredTextPort, TextTable
from app.domain.text_repair import repair_mojibake

logger = logging.getLogger(__name__)

# Lotes de 10,000 renglones: el mínimo de CLAUDE.md §6.3. Con ~77,000 notas
# en el índice son 8 lotes; más grande no gana nada y alarga cada transacción.
BATCH_SIZE = 10_000
# CLAUDE.md §2.6: 5 ejemplos reales antes de procesar datos completos.
SAMPLE_SIZE = 5


@dataclass(frozen=True, slots=True)
class RepairExample:
    """Un texto antes y después de repararlo.

    Attributes:
        table: Tabla.
        row_id: Llave del renglón.
        column: Columna.
        before: Texto guardado.
        after: Texto reparado.
    """

    table: TextTable
    row_id: int
    column: str
    before: str
    after: str


@dataclass(slots=True)
class RepairReport:
    """Resultado de recorrer una tabla.

    Attributes:
        table: Tabla recorrida.
        scanned: Renglones leídos.
        changed: Renglones con al menos un texto reparado.
        applied: Si los cambios se guardaron.
        examples: Primeros ejemplos encontrados (hasta ``SAMPLE_SIZE``).
    """

    table: TextTable
    applied: bool
    scanned: int = 0
    changed: int = 0
    examples: list[RepairExample] = field(default_factory=list)


class RepairStoredText:
    """Recorre una tabla y repara sus textos.

    Args:
        store: Lectura y guardado de los textos.
        batch_size: Renglones por lote.
        sample_size: Ejemplos que se conservan para mostrar.
    """

    def __init__(
        self, store: StoredTextPort, batch_size: int = BATCH_SIZE, sample_size: int = SAMPLE_SIZE
    ) -> None:
        self._store = store
        self._batch_size = batch_size
        self._sample_size = sample_size

    async def run(self, table: TextTable, *, apply: bool) -> RepairReport:
        """Recorre ``table`` completa.

        Args:
            table: Tabla a revisar.
            apply: ``True`` guarda los cambios; ``False`` solo cuenta y
                junta ejemplos.

        Returns:
            Cuántos renglones se leyeron, cuántos cambian y ejemplos.
        """
        report = RepairReport(table=table, applied=apply)
        after_id = 0
        while rows := await self._store.fetch(table, after_id, self._batch_size):
            repaired = [r for r in (self._repair(table, row, report) for row in rows) if r]
            if apply and repaired:
                await self._store.save(table, repaired)
            report.scanned += len(rows)
            report.changed += len(repaired)
            after_id = rows[-1].row_id
            logger.debug(
                "Lote revisado",
                extra={
                    "table": table,
                    "scanned": report.scanned,
                    "changed": report.changed,
                    "applied": apply,
                },
            )
        return report

    def _repair(self, table: TextTable, row: StoredRow, report: RepairReport) -> StoredRow | None:
        fields = {
            column: repair_mojibake(value) if value is not None else None
            for column, value in row.fields.items()
        }
        changed = [column for column, value in row.fields.items() if fields[column] != value]
        if not changed:
            return None
        for column in changed:
            if len(report.examples) < self._sample_size:
                report.examples.append(
                    RepairExample(
                        table=table,
                        row_id=row.row_id,
                        column=column,
                        before=row.fields[column] or "",
                        after=fields[column] or "",
                    )
                )
        return StoredRow(row_id=row.row_id, fields=fields)
