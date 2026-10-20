"""Región geográfica: país, estado, municipio/alcaldía o localidad.

Es la entidad del catálogo ``regions`` (ADR-0002) vista por el resto del
sistema. Las geometrías completas no viajan aquí: solo el punto
representativo y el rectángulo que la contiene, que es lo que necesitan la
interfaz (volar la cámara) y la API; las formas llegan por PMTiles.

No hace: no sabe de SQL ni de JSON.
"""

from dataclasses import dataclass
from enum import StrEnum


class RegionLevel(StrEnum):
    """Nivel de una región, de lo más general a lo más específico."""

    COUNTRY = "country"
    STATE = "state"
    MUNICIPALITY = "municipality"
    LOCALITY = "locality"

    @property
    def depth(self) -> int:
        """Profundidad en la jerarquía: 0 para país, 3 para localidad."""
        return list(RegionLevel).index(self)


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """Punto en grados (WGS 84).

    Attributes:
        lon: Longitud, de -180 a 180.
        lat: Latitud, de -90 a 90.
    """

    lon: float
    lat: float


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Rectángulo que contiene a la región, en grados.

    Attributes:
        west: Longitud mínima.
        south: Latitud mínima.
        east: Longitud máxima.
        north: Latitud máxima.
    """

    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True, slots=True)
class RegionRef:
    """Referencia corta a una región (para migas de pan).

    Attributes:
        id: Identificador.
        level: Nivel.
        code: Clave INEGI o ISO-A3.
        name: Nombre original.
    """

    id: int
    level: RegionLevel
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class Region:
    """Región del catálogo.

    Attributes:
        id: Identificador.
        level: Nivel.
        code: Clave INEGI (``09007``) o ISO-A3 (``COL``).
        name: Nombre original, con acentos.
        name_norm: Nombre normalizado para comparar (conserva la Ñ).
        display_prefix: "Alcaldía", "Municipio", "Estado"...
        country_code: País al que pertenece (ISO-A3).
        parent_id: Región padre (``None`` en países).
        point: Punto representativo, siempre dentro de la región.
        bbox: Rectángulo que la contiene.
        focus_bbox: Rectángulo de su parte principal, sin islas ni territorios
            lejanos (``None`` si es de una sola parte). Ver ``focus``.
        has_polygon: ``False`` en localidades que solo tienen punto.
        aliases: Otros nombres con que se le conoce ("CDMX").
        population: Habitantes, si la fuente los trae.
    """

    id: int
    level: RegionLevel
    code: str
    name: str
    name_norm: str
    display_prefix: str
    country_code: str
    parent_id: int | None
    point: GeoPoint
    bbox: BoundingBox
    has_polygon: bool
    aliases: tuple[str, ...]
    population: int | None
    focus_bbox: BoundingBox | None = None

    @property
    def focus(self) -> BoundingBox:
        """Rectángulo para encuadrar la región en un mapa.

        El de su parte principal si tiene varias (Francia sin Guayana ni
        Reunión); si no, el ``bbox`` completo.
        """
        return self.focus_bbox or self.bbox

    @property
    def display_name(self) -> str:
        """Nombre para mostrar en tooltips y tarjetas.

        Municipios y localidades llevan su prefijo ("Alcaldía Iztapalapa",
        "Municipio Acuña"); países y estados se muestran solo con su nombre
        ("Jalisco", no "Estado Jalisco").
        """
        if self.level in (RegionLevel.MUNICIPALITY, RegionLevel.LOCALITY):
            return f"{self.display_prefix} {self.name}"
        return self.name

    def ref(self) -> RegionRef:
        """Devuelve la referencia corta de esta región."""
        return RegionRef(self.id, self.level, self.code, self.name)


@dataclass(frozen=True, slots=True)
class RegionDetail:
    """Región con sus ancestros, para las migas de pan.

    Attributes:
        region: La región.
        ancestors: Del más general al más cercano, por ejemplo
            [México, Ciudad de México] para Iztapalapa.
    """

    region: Region
    ancestors: tuple[RegionRef, ...]

    @property
    def breadcrumb(self) -> str:
        """Ruta legible: "México › Ciudad de México › Iztapalapa"."""
        return " › ".join([*(a.name for a in self.ancestors), self.region.name])
