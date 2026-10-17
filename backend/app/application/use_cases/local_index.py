"""Buscar un concepto en el índice local (pestaña temporal "Notas", ADR-0014).

Junta dos piezas que ya existen:

1. ``PreviewConceptQueries`` arma la consulta del índice local para el
   concepto, la región y los días (las mismas reglas que "Probar concepto").
2. ``ExecuteQueries`` la ejecuta: queda en ``provider_queries`` igual que una
   búsqueda real (CLAUDE.md §8) y no gasta créditos.

Es una vista de prueba: la Fase 5 la sustituye por la API definitiva de
búsquedas, que consulta todos los proveedores.

No hace: no consulta SearchApi ni geolocaliza (eso es F4).
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date

from app.application.clock import MEXICO_CITY
from app.application.use_cases.concepts import PreviewConceptQueries, QueryPreview
from app.application.use_cases.execute_queries import ExecuteQueries, QueryOutcome
from app.domain.errors import InvalidRequestError
from app.domain.queries import Provider


@dataclass(frozen=True, slots=True)
class LocalIndexSearch:
    """Resultado de buscar un concepto en el índice local.

    Attributes:
        preview: Concepto, región, rango y la consulta armada.
        outcome: Qué respondió el índice (notas, estado, mensaje).
        by_day: Notas por día (hora de la Ciudad de México), del más viejo al
            más nuevo.
        by_source: Notas por fuente (``gdelt_ngrams``, ``gdelt_gkg``...).
    """

    preview: QueryPreview
    outcome: QueryOutcome
    by_day: tuple[tuple[date, int], ...]
    by_source: tuple[tuple[str, int], ...]


class SearchLocalIndex:
    """Busca un concepto guardado en el índice local."""

    def __init__(self, preview: PreviewConceptQueries, execute: ExecuteQueries) -> None:
        """Recibe los dos casos de uso que reutiliza.

        Args:
            preview: Arma las consultas ("Probar concepto").
            execute: Las ejecuta con registro.
        """
        self._preview = preview
        self._execute = execute

    async def run(self, concept_id: int, region_id: int, days: int) -> LocalIndexSearch:
        """Arma y ejecuta la consulta del índice local.

        Args:
            concept_id: Concepto guardado.
            region_id: Región.
            days: Últimos N días (1 a 90).

        Returns:
            Las notas encontradas y sus conteos.

        Raises:
            ConceptNotFoundError: Si el concepto no existe.
            RegionNotFoundError: Si la región no existe.
            InvalidRequestError: Si los días están fuera de rango.
        """
        preview = await self._preview.for_saved(concept_id, region_id, days)
        query = next((q for q in preview.queries if q.provider is Provider.LOCAL_INDEX), None)
        if query is None:  # pragma: no cover — build_queries siempre incluye el índice local
            raise InvalidRequestError("No se pudo armar la consulta del índice local.")
        result = await self._execute.execute([query])
        outcome = result.outcomes[0]
        days_count = Counter(
            a.published_at.astimezone(MEXICO_CITY).date()
            for a in outcome.articles
            if a.published_at is not None
        )
        sources = Counter(str(a.raw.get("source", "")) for a in outcome.articles)
        return LocalIndexSearch(
            preview=preview,
            outcome=outcome,
            by_day=tuple(sorted(days_count.items())),
            by_source=tuple(sources.most_common()),
        )
