"""Reglas puras de los reportes (especificación §15, ADR-0018).

- **Subregiones:** la tabla y el mapa del reporte cuentan las notas un nivel
  abajo de la región buscada: país → estados, estado → municipios,
  municipio → localidades. Una localidad se cuenta a sí misma.
- **Dentro de la región:** solo las notas ubicadas en la región buscada entran
  en la tabla; las notas de fuera se cuentan aparte (§9 paso 7: no se borran).

No hace: no consulta la base ni dibuja.
"""

from app.domain.aggregates import AggregateLevel, NoteLocation
from app.domain.geocoding import MEXICO_ISO3
from app.domain.region import RegionLevel

_SUBREGION = {
    RegionLevel.COUNTRY: AggregateLevel.STATE,
    RegionLevel.STATE: AggregateLevel.MUNICIPALITY,
    RegionLevel.MUNICIPALITY: AggregateLevel.LOCALITY,
    RegionLevel.LOCALITY: AggregateLevel.LOCALITY,
}


def subregion_level(level: RegionLevel, code: str) -> AggregateLevel:
    """Nivel al que se cuentan las notas en el reporte de una región.

    Args:
        level: Nivel de la región buscada.
        code: Su clave (INEGI o ISO-A3).

    Returns:
        El nivel de abajo (una localidad se queda en localidad). Otro país
        se cuenta a sí mismo: el catálogo solo tiene estados de México.

    Example:
        >>> subregion_level(RegionLevel.STATE, "14")
        <AggregateLevel.MUNICIPALITY: 'municipality'>
    """
    if level is RegionLevel.COUNTRY and code != MEXICO_ISO3:
        return AggregateLevel.COUNTRY
    return _SUBREGION[level]


def is_inside(note: NoteLocation, region_code: str, region_level: RegionLevel) -> bool:
    """Dice si la ubicación principal de una nota cae dentro de la región buscada.

    Igual que la pestaña "Dentro" de la pantalla (§9 paso 7): una nota que
    solo dice "México" no se sabe si es de Jalisco, así que queda fuera.

    Args:
        note: Ubicación principal de la nota (con clave).
        region_code: Clave de la región buscada (INEGI o ISO-A3).
        region_level: Nivel de la región buscada.

    Returns:
        En un país, si la nota es de ese país. Dentro de México, si su clave
        empieza con la de la región (``14`` contiene a ``14`` y a ``14039``, §6).
    """
    if note.code is None:
        return False
    if region_level is RegionLevel.COUNTRY:
        return note.country_code == region_code
    return note.country_code == MEXICO_ISO3 and note.code.startswith(region_code)
