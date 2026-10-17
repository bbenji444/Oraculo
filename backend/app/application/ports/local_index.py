"""Puerto de las estadísticas del índice local (pestaña temporal "Notas", ADR-0014).

La implementación está en ``app/adapters/persistence/news_index_repository.py``.

No hace: no busca notas (eso es el proveedor ``indice_local``).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceStats:
    """Cuánto hay de una fuente en el índice.

    Attributes:
        source: ``gdelt_gkg``, ``gdelt_ngrams`` o ``rss:<medio>``.
        notes: Notas guardadas.
        with_body: Notas que conservan frases del cuerpo.
        body_bytes: Bytes que ocupan esas frases en disco (ya comprimidas).
        oldest: Nota más vieja (UTC), o ``None``.
        newest: Nota más nueva (UTC), o ``None``.
    """

    source: str
    notes: int
    with_body: int
    body_bytes: int
    oldest: datetime | None
    newest: datetime | None


@dataclass(frozen=True, slots=True)
class IndexStats:
    """Resumen del índice.

    Attributes:
        sources: Una entrada por fuente.
        total_bytes: Bytes de la tabla con sus índices.
        last_run_at: Última corrida exitosa de la ingesta (UTC), o ``None``.
    """

    sources: tuple[SourceStats, ...]
    total_bytes: int
    last_run_at: datetime | None


class IndexStatsPort(Protocol):
    """Lectura del resumen del índice local."""

    async def stats(self) -> IndexStats:
        """Resumen por fuente, tamaño y última corrida.

        Returns:
            El resumen.
        """
        ...
