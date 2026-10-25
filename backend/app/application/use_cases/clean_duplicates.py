"""Quitar del índice local las notas repetidas que entraron antes de F12.1b.

Lee todas las llaves del índice por lotes con cursor (CLAUDE.md §6.3),
decide con ``plan_index_cleanup`` qué sobra y, solo si se le pide, borra y
recalcula huellas por lotes de ``BATCH_SIZE`` con un commit por lote.

Sin ``apply`` no escribe nada: da conteos por motivo y ejemplos reales
(CLAUDE.md §2.6). Lo usa ``make limpiar-duplicados``.

No hace: no toca ``articles`` (ahí las repetidas se juntan en historias,
sin borrar, porque pueden estar en casos) ni pide confirmación.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field

from app.application.ports.index_cleanup import IndexCleanupPort
from app.domain.index_cleanup import CleanupReason, IndexKey, Removal, plan_index_cleanup

logger = logging.getLogger(__name__)

# Lotes de 10,000: el mínimo de CLAUDE.md §6.3 (el índice tiene ~77,000 notas).
BATCH_SIZE = 10_000
# CLAUDE.md §2.6: 5 ejemplos reales antes de procesar datos completos.
SAMPLE_SIZE = 5


@dataclass(slots=True)
class CleanupReport:
    """Resultado de revisar (y, si se pidió, limpiar) el índice.

    Attributes:
        applied: Si los cambios se guardaron.
        scanned: Notas revisadas.
        by_reason: Cuántas sobran por motivo.
        rehashed: Huellas recalculadas (o por recalcular).
        examples: Ejemplos: uno por motivo primero, luego en orden.
    """

    applied: bool
    scanned: int = 0
    by_reason: Counter[CleanupReason] = field(default_factory=Counter)
    rehashed: int = 0
    examples: list[Removal] = field(default_factory=list)

    @property
    def removed(self) -> int:
        """Total de notas que sobran."""
        return sum(self.by_reason.values())


def _examples(removals: list[Removal], size: int) -> list[Removal]:
    """Un ejemplo de cada motivo primero, para que se vean todos los casos."""
    first: dict[CleanupReason, Removal] = {}
    for removal in removals:
        first.setdefault(removal.reason, removal)
    chosen = list(first.values())[:size]
    taken = {id(r) for r in chosen}
    for removal in removals:
        if len(chosen) >= size:
            break
        if id(removal) not in taken:
            chosen.append(removal)
    return chosen


class CleanIndexDuplicates:
    """Revisa el índice completo y quita lo repetido.

    Args:
        store: Lectura, borrado y recálculo de huellas.
        batch_size: Notas por lote.
        sample_size: Ejemplos que se conservan.
    """

    def __init__(
        self, store: IndexCleanupPort, batch_size: int = BATCH_SIZE, sample_size: int = SAMPLE_SIZE
    ) -> None:
        self._store = store
        self._batch_size = batch_size
        self._sample_size = sample_size

    async def run(self, *, apply: bool) -> CleanupReport:
        """Revisa (y, con ``apply``, limpia) el índice.

        Args:
            apply: ``True`` borra y recalcula; ``False`` solo cuenta.

        Returns:
            Conteos por motivo, huellas y ejemplos.
        """
        keys: list[IndexKey] = []
        after_id = 0
        while batch := await self._store.fetch_keys(after_id, self._batch_size):
            keys.extend(batch)
            after_id = batch[-1].note_id
        plan = plan_index_cleanup(keys)
        report = CleanupReport(
            applied=apply,
            scanned=len(keys),
            by_reason=Counter(r.reason for r in plan.removals),
            rehashed=len(plan.rehash),
            examples=_examples(plan.removals, self._sample_size),
        )
        if apply:
            ids = [r.note.note_id for r in plan.removals]
            # Primero se borra: así ninguna huella nueva choca con la de una
            # repetida que todavía estuviera en la tabla.
            for start in range(0, len(ids), self._batch_size):
                await self._store.delete(ids[start : start + self._batch_size])
            for start in range(0, len(plan.rehash), self._batch_size):
                await self._store.rehash(plan.rehash[start : start + self._batch_size])
            logger.info(
                "Índice limpio",
                extra={"removed": report.removed, "rehashed": report.rehashed},
            )
        return report
