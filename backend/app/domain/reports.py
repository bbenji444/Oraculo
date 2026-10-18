"""Reglas puras de los reportes (especificación §15, ADR-0018).

- **Subregiones:** la tabla y el mapa del reporte cuentan las notas un nivel
  abajo de la región buscada: país → estados, estado → municipios,
  municipio → localidades. Una localidad se cuenta a sí misma.
- **Dentro de la región:** solo las subregiones de la región buscada entran
  en la tabla; las notas de fuera se cuentan aparte (§9 paso 7: no se borran).

No hace: no consulta la base ni dibuja.
"""

from app.domain.aggregates import AggregateLevel
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


def is_inside(code: str, region_code: str, region_level: RegionLevel) -> bool:
    """Dice si una subregión (por su clave) pertenece a la región buscada.

    Args:
        code: Clave de la subregión (INEGI, o ISO-A3 en otro país).
        region_code: Clave de la región buscada (INEGI o ISO-A3).
        region_level: Nivel de la región buscada.

    Returns:
        En México (país), todo estado está dentro; otro país solo se contiene
        a sí mismo. Dentro de México, si la clave empieza con la de la región
        (``14`` contiene a ``14039``, §6).
    """
    if region_level is RegionLevel.COUNTRY:
        return region_code in (MEXICO_ISO3, code)
    return code.startswith(region_code)
