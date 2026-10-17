"""Catálogo de prueba en memoria para el geolocalizador (§11: "catálogo de prueba")."""

from difflib import SequenceMatcher

from app.domain.geocoding import Place
from app.domain.names import normalize_name
from app.domain.region import RegionLevel


def place(
    region_id: int,
    code: str,
    level: RegionLevel,
    name: str,
    *,
    display: str | None = None,
    country: str = "MEX",
) -> Place:
    return Place(region_id, code, level, name, display or name, country, -99.0, 19.0)


MEXICO = place(1, "MEX", RegionLevel.COUNTRY, "México")
SPAIN = place(2, "ESP", RegionLevel.COUNTRY, "España", country="ESP")
CDMX = place(10, "09", RegionLevel.STATE, "Ciudad de México")
EDOMEX = place(11, "15", RegionLevel.STATE, "México")
COAHUILA = place(12, "05", RegionLevel.STATE, "Coahuila de Zaragoza")
NUEVO_LEON = place(13, "19", RegionLevel.STATE, "Nuevo León")
IZTAPALAPA = place(
    20, "09007", RegionLevel.MUNICIPALITY, "Iztapalapa", display="Alcaldía Iztapalapa"
)
IZTAPALAPA_LOC = place(21, "090070001", RegionLevel.LOCALITY, "Iztapalapa")
SAN_PEDRO_COAH = place(22, "05033", RegionLevel.MUNICIPALITY, "San Pedro")
SAN_PEDRO_COAH_LOC = place(23, "050330001", RegionLevel.LOCALITY, "San Pedro")
SAN_PEDRO_GG = place(24, "19019", RegionLevel.MUNICIPALITY, "San Pedro Garza García")
SAN_PEDRO_PUEBLA_LOC = place(25, "211140009", RegionLevel.LOCALITY, "San Pedro")
# Otra localidad "San Pedro" en Coahuila, fuera del municipio San Pedro.
SAN_PEDRO_COAH_LOC2 = place(29, "050350010", RegionLevel.LOCALITY, "San Pedro")
NEZA = place(26, "15058", RegionLevel.MUNICIPALITY, "Nezahualcóyotl")
PENON = place(27, "090170999", RegionLevel.LOCALITY, "Peñón de los Baños")
# Señuelo: el mismo nombre sin Ñ. Si la Ñ se convirtiera en N, coincidiría.
PENON_SIN_ENIE = place(28, "110030999", RegionLevel.LOCALITY, "Penon de los Banos")

ALIASES: dict[int, tuple[str, ...]] = {
    CDMX.region_id: ("CDMX", "la capital del país", "DF"),
    EDOMEX.region_id: ("Edomex", "Estado de México"),
    COAHUILA.region_id: ("Coahuila",),
    SAN_PEDRO_GG.region_id: ("San Pedro",),
    NEZA.region_id: ("Neza",),
}
ALL = (
    MEXICO,
    SPAIN,
    CDMX,
    EDOMEX,
    COAHUILA,
    NUEVO_LEON,
    IZTAPALAPA,
    IZTAPALAPA_LOC,
    SAN_PEDRO_COAH,
    SAN_PEDRO_COAH_LOC,
    SAN_PEDRO_GG,
    SAN_PEDRO_PUEBLA_LOC,
    SAN_PEDRO_COAH_LOC2,
    NEZA,
    PENON,
    PENON_SIN_ENIE,
)


def _names(p: Place) -> set[str]:
    return {normalize_name(p.name), *(normalize_name(a) for a in ALIASES.get(p.region_id, ()))}


class FakeGazetteer:
    """Busca en ``ALL`` como lo haría ``regions`` (nombre o alias normalizados)."""

    async def exact(self, name_norm: str) -> list[Place]:
        return [p for p in ALL if name_norm in _names(p)]

    async def similar(self, name_norm: str, min_similarity: float) -> list[tuple[Place, float]]:
        scored = [
            (p, SequenceMatcher(None, name_norm, normalize_name(p.name)).ratio())
            for p in ALL
            if p.country_code == "MEX"
        ]
        good = [(p, s) for p, s in scored if s >= min_similarity]
        if not good:
            return []
        best = max(s for _, s in good)
        return [(p, s) for p, s in good if s == best]

    async def country(self, name_norm: str) -> Place | None:
        return next(
            (p for p in ALL if p.level is RegionLevel.COUNTRY and name_norm in _names(p)), None
        )

    async def by_code(self, code: str) -> Place | None:
        return next((p for p in ALL if p.code == code), None)
