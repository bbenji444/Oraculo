"""Conteos por región para el mapa de calor (especificación §13 y §14).

Cada nota cuenta una vez, en su **ubicación principal**, subida al nivel que
se pide por el prefijo de la clave INEGI (2 dígitos = estado, 5 = municipio;
§6). Una nota menos precisa que el nivel **no se reparte**: se cuenta aparte
como ``coarser``, para no inventar precisión (§11). Las de otro país van en
``abroad`` en los niveles de México.

No hace: no consulta la base ni sabe nombres ni coordenadas.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.geocoding import MEXICO_ISO3, Precision

# Largo de la clave INEGI por nivel (§6): estado 2, municipio 5.
STATE_CODE_LENGTH = 2
MUNICIPALITY_CODE_LENGTH = 5


class AggregateLevel(StrEnum):
    """Nivel al que se suben los conteos."""

    COUNTRY = "country"
    STATE = "state"
    MUNICIPALITY = "municipality"


# Precisiones que alcanzan cada nivel de México.
_REACHES = {
    AggregateLevel.STATE: {Precision.STATE, Precision.MUNICIPALITY, Precision.LOCALITY},
    AggregateLevel.MUNICIPALITY: {Precision.MUNICIPALITY, Precision.LOCALITY},
}
_CODE_LENGTH = {
    AggregateLevel.STATE: STATE_CODE_LENGTH,
    AggregateLevel.MUNICIPALITY: MUNICIPALITY_CODE_LENGTH,
}


@dataclass(frozen=True, slots=True)
class NoteLocation:
    """La ubicación principal de una nota (o su falta).

    Attributes:
        code: Clave de la región (INEGI o ISO-A3), o ``None`` sin ubicación.
        country_code: País de esa región (ISO-A3).
        precision: Precisión de la ubicación.
    """

    code: str | None
    country_code: str | None
    precision: Precision


@dataclass(slots=True)
class Aggregation:
    """Resultado de agrupar.

    Attributes:
        counts: Notas por clave de región del nivel pedido.
        coarser: Notas ubicadas con menos precisión que el nivel.
        abroad: Notas de otro país (solo en niveles de México).
        unlocated: Notas sin ubicación.
    """

    counts: Counter[str] = field(default_factory=Counter)
    coarser: int = 0
    abroad: int = 0
    unlocated: int = 0

    @property
    def total(self) -> int:
        """Todas las notas contadas."""
        return sum(self.counts.values()) + self.coarser + self.abroad + self.unlocated


def aggregate(notes: Iterable[NoteLocation], level: AggregateLevel) -> Aggregation:
    """Agrupa las notas por región del nivel pedido.

    Args:
        notes: Ubicación principal de cada nota.
        level: País, estado o municipio.

    Returns:
        Conteos por clave y lo que no cabe en el nivel.

    Example:
        >>> aggregate([NoteLocation("14039", "MEX", Precision.MUNICIPALITY)], AggregateLevel.STATE)
        Aggregation(counts=Counter({'14': 1}), coarser=0, abroad=0, unlocated=0)
    """
    result = Aggregation()
    for note in notes:
        if note.code is None or note.country_code is None:
            result.unlocated += 1
        elif level is AggregateLevel.COUNTRY:
            result.counts[note.country_code] += 1
        elif note.country_code != MEXICO_ISO3:
            result.abroad += 1
        elif note.precision not in _REACHES[level]:
            result.coarser += 1
        else:
            result.counts[note.code[: _CODE_LENGTH[level]]] += 1
    return result
