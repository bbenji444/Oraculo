"""Reglas de una búsqueda completa (especificación §9).

- **Estado final:** ``completed`` si todo salió; ``partial`` si alguna etapa
  falló en más de la mitad de las notas o algún proveedor falló;
  ``failed`` si no se pudo consultar a ningún proveedor.
- **Dentro de la región:** una nota está dentro si su ubicación principal
  cae en la región buscada (por el prefijo de la clave INEGI, §6). Las de
  fuera **no se borran**: se muestran aparte.

No hace: no consulta nada ni guarda (eso es el caso de uso del pipeline).
"""

from dataclasses import dataclass
from enum import StrEnum

from app.domain.geocoding import Place
from app.domain.region import RegionLevel

# §9: "Si más del 50% de las noticias falla en una etapa, la búsqueda queda
# en partial".
MAX_FAILED_SHARE = 0.5


class SearchStatus(StrEnum):
    """Columna ``searches.status``."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"

    @property
    def is_finished(self) -> bool:
        """Si ya no va a cambiar (bien, a medias o con falla): tiene reporte."""
        return self in (SearchStatus.COMPLETED, SearchStatus.PARTIAL, SearchStatus.FAILED)


class Stage(StrEnum):
    """Etapas del pipeline (§9), para ``progress`` y ``processing_errors``."""

    PLAN = "plan"
    QUERY = "query"
    DEDUPE = "dedupe"
    EXTRACT = "extract"
    ENRICH = "enrich"
    GEOCODE = "geocode"
    FILTER = "filter"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class StageCount:
    """Cuántas notas pasaron y cuántas fallaron en una etapa.

    Attributes:
        stage: Etapa.
        total: Notas que entraron.
        failed: Notas que fallaron.
    """

    stage: Stage
    total: int
    failed: int

    @property
    def failed_too_much(self) -> bool:
        """``True`` si falló más de la mitad (§9)."""
        return self.total > 0 and self.failed / self.total > MAX_FAILED_SHARE


def final_status(
    queries_ok: int, queries_failed: int, stages: tuple[StageCount, ...]
) -> SearchStatus:
    """Decide cómo terminó la búsqueda.

    Args:
        queries_ok: Consultas a proveedores que respondieron.
        queries_failed: Consultas que fallaron.
        stages: Conteos de las etapas por nota.

    Returns:
        ``failed`` si ningún proveedor respondió; ``partial`` si alguno
        falló o alguna etapa falló en más de la mitad; si no, ``completed``.
    """
    if queries_ok == 0:
        return SearchStatus.FAILED
    if queries_failed > 0 or any(s.failed_too_much for s in stages):
        return SearchStatus.PARTIAL
    return SearchStatus.COMPLETED


def in_region(primary: Place | None, searched: Place) -> bool | None:
    """Dice si la ubicación principal de una nota cae en la región buscada.

    Args:
        primary: Ubicación principal de la nota, si tiene.
        searched: Región de la búsqueda.

    Returns:
        ``None`` si la nota no tiene ubicación (va a "Sin ubicación");
        ``True``/``False`` según el prefijo de la clave o el país.
    """
    if primary is None:
        return None
    if searched.level is RegionLevel.COUNTRY:
        return primary.country_code == searched.code
    return primary.region_id == searched.region_id or searched.contains(primary)
