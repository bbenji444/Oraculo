"""Juntar en historias las notas del mismo hecho (F12.1c, ADR-0026).

- ``GroupStories``: al cerrar cada búsqueda (y cada corrida automática),
  agrupa las notas que encontró con las de su ventana de fechas.
- ``RegroupAllStories``: ``make agrupar-historias``. Recalcula todas desde
  cero en orden cronológico; sin ``apply`` solo cuenta y da ejemplos.

Nada se borra: solo cambia ``articles.story_id``.

No hace: no decide la regla (``app.domain.stories``) ni pide confirmación.
"""

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from app.application.ports.stories import StoryStorePort
from app.domain.stories import STORY_SPAN, Similarity, StoryNote, assign_stories

logger = logging.getLogger(__name__)

# Lotes de lectura (CLAUDE.md §6.3); hoy hay ~1,450 notas.
BATCH_SIZE = 10_000
# CLAUDE.md §2.6: 5 ejemplos reales antes de aplicar a todo.
SAMPLE_SIZE = 5


class GroupStories:
    """Agrupa las notas de una búsqueda con sus vecinas en fecha.

    Args:
        store: Lectura y guardado.
        similarity: Parecido de títulos (``fuzz.ratio``).
        token_similarity: Parecido por palabras (``token_set_ratio``).
    """

    def __init__(
        self, store: StoryStorePort, similarity: Similarity, token_similarity: Similarity
    ) -> None:
        self._store = store
        self._similarity = similarity
        self._token_similarity = token_similarity

    async def run(self, article_ids: Sequence[int]) -> int:
        """Agrupa las notas que todavía no tienen historia.

        Args:
            article_ids: Notas de la búsqueda.

        Returns:
            Cuántas notas cambiaron de historia.
        """
        if not article_ids:
            return 0
        window = await self._store.window(article_ids, STORY_SPAN)
        new = [n for n in window.targets if n.story_id is None]
        existing = [*window.neighbors, *(n for n in window.targets if n.story_id is not None)]
        changes = assign_stories(existing, new, self._similarity, self._token_similarity)
        if changes:
            await self._store.save(changes)
        return len(changes)


def _spread(stories: list[list[StoryNote]], size: int) -> list[list[StoryNote]]:
    """Ejemplos variados: las dos más grandes y el resto repartido entre las chicas.

    Las grandes son fáciles de juzgar; los errores suelen estar en las de 2 o 3
    notas, así que también se muestran.
    """
    if len(stories) <= size:
        return stories
    big = stories[:2]
    rest = stories[2:]
    step = len(rest) / (size - len(big))
    return big + [rest[int(i * step)] for i in range(size - len(big))]


@dataclass(slots=True)
class RegroupReport:
    """Resultado de recalcular todas las historias.

    Attributes:
        applied: Si se guardó.
        scanned: Notas revisadas.
        stories: Historias que quedan (de 2 notas o más).
        grouped: Notas que quedan en alguna historia.
        changed: Notas cuya historia cambia respecto a lo guardado.
        examples: Las historias más grandes (hasta ``SAMPLE_SIZE``), cada una
            con sus notas en orden de fecha.
    """

    applied: bool
    scanned: int = 0
    stories: int = 0
    grouped: int = 0
    changed: int = 0
    examples: list[list[StoryNote]] = field(default_factory=list)


class RegroupAllStories:
    """Recalcula las historias de todas las notas.

    Args:
        store: Lectura y guardado.
        similarity: Parecido de títulos.
        token_similarity: Parecido por palabras.
        batch_size: Notas por lote de lectura.
        sample_size: Historias de ejemplo.
    """

    def __init__(
        self,
        store: StoryStorePort,
        similarity: Similarity,
        token_similarity: Similarity,
        batch_size: int = BATCH_SIZE,
        sample_size: int = SAMPLE_SIZE,
    ) -> None:
        self._store = store
        self._similarity = similarity
        self._token_similarity = token_similarity
        self._batch_size = batch_size
        self._sample_size = sample_size

    async def run(self, *, apply: bool) -> RegroupReport:
        """Recalcula desde cero (y, con ``apply``, guarda).

        Args:
            apply: ``True`` guarda; ``False`` solo cuenta.

        Returns:
            Conteos y ejemplos.
        """
        notes: list[StoryNote] = []
        after_id = 0
        while batch := await self._store.fetch_all(after_id, self._batch_size):
            notes.extend(batch)
            after_id = batch[-1].article_id
        fresh = [replace(n, story_id=None) for n in notes]
        assigned = assign_stories([], fresh, self._similarity, self._token_similarity)
        final = {n.article_id: assigned.get(n.article_id) for n in notes}
        changes = {
            n.article_id: final[n.article_id] for n in notes if n.story_id != final[n.article_id]
        }
        members: dict[int, list[StoryNote]] = defaultdict(list)
        for n in notes:
            story_id = final[n.article_id]
            if story_id is not None:
                members[story_id].append(n)
        biggest = sorted(members.values(), key=lambda m: (-len(m), min(n.article_id for n in m)))
        report = RegroupReport(
            applied=apply,
            scanned=len(notes),
            stories=len(members),
            grouped=sum(len(m) for m in members.values()),
            changed=len(changes),
            examples=[
                sorted(m, key=lambda n: n.published_at) for m in _spread(biggest, self._sample_size)
            ],
        )
        if apply and changes:
            await self._store.save(changes)
            logger.info(
                "Historias recalculadas",
                extra={"stories": report.stories, "changed": report.changed},
            )
        return report
