"""Clasificar notas por categoría (el delito), por lotes (F12.4, ADR-0029).

- ``ClassifyArticles.run``: al cerrar cada búsqueda (y cada corrida
  automática), clasifica las notas que encontró y que no tienen categoría de
  la versión vigente del prompt.
- ``ClassifyArticles.sample`` y ``run_pending``: ``make clasificar``, con 5
  ejemplos sin guardar o con todas las pendientes.

Cada lote va a la IA con título y resumen (nunca el texto, §8). Lo que la
IA no responda se queda sin categoría y se intenta en la siguiente pasada;
lo que responda fuera del catálogo va a «Otros» con su etiqueta.

No hace: no pide confirmación ni decide la regla de «Otros» (dominio).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.application.ports.categories import CategoryStorePort
from app.application.ports.llm import (
    CategoryOption,
    ClassificationNote,
    ClassificationRequest,
    ClassifierPort,
)
from app.domain.categories import CategoryChoice, choose_category, other_category
from app.domain.enrichment import LLMUsage

# Notas por llamada a la IA (``CLASSIFY_BATCH_SIZE`` del adaptador): ~2,600
# tokens de prompt por lote.
BATCH_SIZE = 25
# CLAUDE.md §2.6: 5 ejemplos reales antes de clasificar en masa.
SAMPLE_SIZE = 5
NO_USAGE = LLMUsage(0, 0)


@dataclass(slots=True)
class ClassifyReport:
    """Resultado de clasificar.

    Attributes:
        classified: Notas que quedaron con categoría.
        usage: Tokens de la IA (también de lotes que fallaron).
        choices: Lo que se eligió, nota por nota (para mostrar ejemplos).
        notes: Título y resumen de las notas clasificadas, por id.
    """

    classified: int = 0
    usage: LLMUsage = NO_USAGE
    choices: list[CategoryChoice] = field(default_factory=list)
    notes: dict[int, ClassificationNote] = field(default_factory=dict)


class ClassifyArticles:
    """Clasifica notas por lotes con la IA.

    Args:
        store: Catálogo y guardado.
        classifier: La IA.
        batch_size: Notas por llamada.
    """

    def __init__(
        self, store: CategoryStorePort, classifier: ClassifierPort, batch_size: int = BATCH_SIZE
    ) -> None:
        self._store = store
        self._classifier = classifier
        self._batch_size = batch_size

    @property
    def version(self) -> str:
        """Versión del prompt con que se clasifica."""
        return self._classifier.classify_prompt_version

    async def run(self, article_ids: Sequence[int]) -> ClassifyReport:
        """Clasifica y guarda las notas de una búsqueda que faltan.

        Args:
            article_ids: Notas de la búsqueda.

        Returns:
            Cuántas se clasificaron y cuántos tokens costó.

        Raises:
            ClassificationError, ProviderError: Si la IA falla (los tokens
                gastados vienen en el error).
        """
        notes = await self._store.pending_notes(article_ids, self.version) if article_ids else []
        return await self._classify(notes, save=True)

    async def sample(
        self, article_ids: Sequence[int] | None = None, size: int = SAMPLE_SIZE
    ) -> ClassifyReport:
        """Clasifica unas pocas notas pendientes **sin guardar** (para revisar).

        Args:
            article_ids: De dónde tomarlas (por ejemplo, las de una búsqueda);
                ``None`` = las primeras pendientes.
            size: Cuántas.

        Returns:
            Lo que se elegiría, con su costo.
        """
        if article_ids is None:
            notes = await self._store.pending_after(0, size, self.version)
        else:
            notes = (await self._store.pending_notes(article_ids, self.version))[:size]
        return await self._classify(notes, save=False)

    async def run_pending(self) -> ClassifyReport:
        """Clasifica y guarda todas las notas pendientes, por lotes con cursor.

        Returns:
            El total clasificado y su costo.
        """
        total = ClassifyReport()
        after_id = 0
        while notes := await self._store.pending_after(after_id, self._batch_size, self.version):
            report = await self._classify(notes, save=True)
            total.classified += report.classified
            total.usage += report.usage
            total.choices.extend(report.choices)
            total.notes.update(report.notes)
            after_id = notes[-1].article_id
        return total

    async def _classify(self, notes: Sequence[ClassificationNote], *, save: bool) -> ClassifyReport:
        report = ClassifyReport()
        if not notes:
            return report
        categories = await self._store.active_categories()
        options = [CategoryOption(c.name, c.description) for c in categories]
        other = other_category(categories).name
        for start in range(0, len(notes), self._batch_size):
            batch = notes[start : start + self._batch_size]
            result = await self._classifier.classify(ClassificationRequest(batch, options, other))
            report.usage += result.usage
            choices = [
                choose_category(label.article_id, label.category, label.raw_label, categories)
                for label in result.labels
            ]
            if save and choices:
                await self._store.save(choices, result.prompt_version)
            report.classified += len(choices)
            report.choices.extend(choices)
            report.notes.update({n.article_id: n for n in batch})
        return report
