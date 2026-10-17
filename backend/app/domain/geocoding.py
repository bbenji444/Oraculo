"""Reglas del geolocalizador: de una mención de lugar a una región del catálogo (§11).

La IA lee la nota y devuelve **menciones** ("Iztapalapa", "San Pedro",
"Madrid"), nunca coordenadas. Aquí se decide, con reglas fijas y sin red,
cuál región del catálogo INEGI corresponde a cada mención y con cuánta
confianza:

- Si una coincidencia está **dentro** de otra (la localidad "Iztapalapa"
  dentro del municipio Iztapalapa), se queda la más general.
- Sin pista de nivel, se prefiere el nivel más general entre las
  coincidencias: en las noticias "San Pedro" es un municipio, no una de las
  532 localidades con ese nombre.
- Si quedan varias, se desempata por los estados que nombra la misma nota
  y luego por la región buscada.
- Si sigue ambigua **no se asigna ese nivel**: se sube al estado si todas
  caen en uno; si no, queda sin ubicar. Nunca se finge precisión.

La población (tercer desempate de §11) no se usa: el catálogo no la trae
(0 de 2,478 municipios con población, medido el 16/10/2026).

No hace: no consulta la base (eso lo hace el caso de uso con un puerto).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from app.domain.names import normalize_name
from app.domain.region import RegionLevel

MEXICO_ISO3 = "MEX"
# Nombres con que la IA puede decir "México" como país.
_MEXICO_NAMES = frozenset({"MEXICO", "ESTADOS UNIDOS MEXICANOS"})
# Confianza según cómo se resolvió la mención (decisión de F4, ajustable con
# datos reales): coincidencia única exacta, desempate por contexto, y "solo
# sabemos el estado" cuando el municipio quedó ambiguo.
EXACT_CONFIDENCE = 0.95
TIEBREAK_CONFIDENCE = 0.8
STATE_FALLBACK_CONFIDENCE = 0.5
# Sin coincidencia exacta se aceptan nombres parecidos (trigramas, §11) con
# confianza reducida: 0.95 × 0.7 ≈ 0.67, apenas sobre el umbral de 0.6.
FUZZY_MIN_SIMILARITY = 0.85
FUZZY_CONFIDENCE_FACTOR = 0.7
# Umbral para ser la ubicación principal (GEO_MIN_CONFIDENCE, §11).
DEFAULT_MIN_CONFIDENCE = 0.6
UNKNOWN_CONFIDENCE = 0.0


class Precision(StrEnum):
    """Qué tan exacta es una ubicación (columna ``precision``)."""

    COUNTRY = "country"
    STATE = "state"
    MUNICIPALITY = "municipality"
    LOCALITY = "locality"
    UNKNOWN = "unknown"


class MentionRole(StrEnum):
    """``event``: donde ocurrió el hecho; ``mentioned``: solo se nombra (§10)."""

    EVENT = "event"
    MENTIONED = "mentioned"


# Del más general al más específico.
_GENERALITY = (
    RegionLevel.COUNTRY,
    RegionLevel.STATE,
    RegionLevel.MUNICIPALITY,
    RegionLevel.LOCALITY,
)


def is_mexico_name(name: str) -> bool:
    """Dice si un texto es el nombre del país ("México"), no del Estado de México.

    El estado 15 se llama oficialmente "México": sin esta regla, cada nota que
    nombra al país parecería nombrar también a ese estado.

    Args:
        name: Texto tal como viene (se normaliza).

    Returns:
        ``True`` si es un nombre del país.
    """
    return normalize_name(name) in _MEXICO_NAMES


@dataclass(frozen=True, slots=True)
class Place:
    """Una región del catálogo, con lo necesario para ubicar y pintar.

    Attributes:
        region_id: Id en ``regions``.
        code: Clave INEGI (``09007``) o ISO-A3 en países (``ESP``).
        level: Nivel de la región.
        name: Nombre oficial.
        display_name: Como se muestra ("Alcaldía Iztapalapa").
        country_code: País (``MEX``).
        lon: Longitud del punto del catálogo (localidad o centroide).
        lat: Latitud del punto del catálogo.
    """

    region_id: int
    code: str
    level: RegionLevel
    name: str
    display_name: str
    country_code: str
    lon: float
    lat: float

    @property
    def state_code(self) -> str | None:
        """Clave del estado que la contiene (el prefijo de 2 dígitos), si es de México."""
        if self.country_code != MEXICO_ISO3 or self.level is RegionLevel.COUNTRY:
            return None
        return self.code[:2]

    @property
    def precision(self) -> Precision:
        """Precisión que da esta región."""
        return Precision(self.level.value)

    def contains(self, other: "Place") -> bool:
        """Dice si ``other`` está dentro de esta región (sin geometría, por clave).

        Args:
            other: Otra región.

        Returns:
            ``True`` si es una región distinta y queda dentro: un país contiene
            todo lo de su país; en México, el prefijo de la clave INEGI dice la
            jerarquía (``09`` contiene a ``09007``).
        """
        if other.region_id == self.region_id:
            return False
        if self.level is RegionLevel.COUNTRY:
            return other.country_code == self.code
        return len(other.code) > len(self.code) and other.code.startswith(self.code)


@dataclass(frozen=True, slots=True)
class Mention:
    """Una mención de lugar tal como la entrega la IA (§10).

    Attributes:
        text: Texto de la mención ("Iztapalapa").
        role: Si ahí ocurrió el hecho o solo se nombra.
        kind_hint: Nivel que sugiere la IA, si lo sugiere.
        state_hint: Estado que sugiere la IA ("Ciudad de México").
        country: País que sugiere la IA ("España").
    """

    text: str
    role: MentionRole
    kind_hint: RegionLevel | None = None
    state_hint: str | None = None
    country: str | None = None

    @property
    def is_abroad(self) -> bool:
        """``True`` si la IA dice que el lugar está en otro país (paso 1 de §11)."""
        if self.country is None:
            return False
        country = normalize_name(self.country)
        return bool(country) and country not in _MEXICO_NAMES


@dataclass(frozen=True, slots=True)
class Resolution:
    """Cómo quedó resuelta una mención.

    Attributes:
        mention: La mención original.
        place: Región elegida, o ``None`` si no se pudo resolver.
        precision: Precisión de la ubicación.
        confidence: Confianza de 0 a 1.
        is_primary: Si es la ubicación principal de la nota.
    """

    mention: Mention
    place: Place | None
    precision: Precision
    confidence: float
    is_primary: bool = False


@dataclass(frozen=True, slots=True)
class Choice:
    """Resultado de desempatar candidatos.

    Attributes:
        place: Región elegida, si quedó una.
        state_code: Si no quedó una pero todas caen en el mismo estado, su
            clave (el caso de uso busca la región del estado).
        confidence: Confianza.
    """

    place: Place | None
    state_code: str | None
    confidence: float


def most_general(candidates: Sequence[Place]) -> list[Place]:
    """Quita las coincidencias que están dentro de otra y se queda con el nivel más general.

    Args:
        candidates: Regiones cuyo nombre o alias coincide con la mención.

    Returns:
        Las candidatas del nivel más general, sin las contenidas en otra.

    Example:
        >>> most_general([iztapalapa_municipio, iztapalapa_localidad])
        [iztapalapa_municipio]
    """
    unique = list({c.region_id: c for c in candidates}.values())
    outer = [c for c in unique if not any(o.contains(c) for o in unique)]
    if not outer:
        return []
    top = min(_GENERALITY.index(c.level) for c in outer)
    return [c for c in outer if _GENERALITY.index(c.level) == top]


def disambiguate(
    candidates: Sequence[Place],
    context_states: Iterable[str],
    searched: Place | None,
) -> Choice:
    """Elige una región entre varias candidatas (paso 4 de §11).

    Args:
        candidates: Candidatas ya filtradas (``most_general``, nivel, estado).
        context_states: Claves de estado que nombra la misma nota.
        searched: Región de la búsqueda, si la hay.

    Returns:
        La elegida con su confianza; o solo el estado común; o nada.
    """
    if not candidates:
        return Choice(None, None, UNKNOWN_CONFIDENCE)
    if len(candidates) == 1:
        return Choice(candidates[0], None, EXACT_CONFIDENCE)
    states = set(context_states)
    by_context = [c for c in candidates if c.state_code in states]
    if len(by_context) == 1:
        return Choice(by_context[0], None, TIEBREAK_CONFIDENCE)
    pool = by_context or list(candidates)
    if searched is not None:
        inside = [c for c in pool if c.region_id == searched.region_id or searched.contains(c)]
        if len(inside) == 1:
            return Choice(inside[0], None, TIEBREAK_CONFIDENCE)
    common = {c.state_code for c in pool}
    if len(common) == 1:
        (state_code,) = common
        if state_code is not None:
            return Choice(None, state_code, STATE_FALLBACK_CONFIDENCE)
    return Choice(None, None, UNKNOWN_CONFIDENCE)


_SPECIFICITY = {
    Precision.UNKNOWN: -1,
    Precision.COUNTRY: 0,
    Precision.STATE: 1,
    Precision.MUNICIPALITY: 2,
    Precision.LOCALITY: 3,
}


def mark_primary(resolutions: Sequence[Resolution], min_confidence: float) -> list[Resolution]:
    """Marca la ubicación principal: el lugar del hecho más específico y confiable (paso 6).

    Args:
        resolutions: Menciones resueltas de una nota.
        min_confidence: Umbral (``GEO_MIN_CONFIDENCE``).

    Returns:
        Las mismas resoluciones, con a lo más una ``is_primary``. Si ningún
        lugar del hecho pasa el umbral, ninguna lo es: la nota queda "sin
        ubicación" y no se pinta en el mapa.
    """
    eligible = [
        (index, r)
        for index, r in enumerate(resolutions)
        if r.mention.role is MentionRole.EVENT
        and r.place is not None
        and r.confidence >= min_confidence
    ]
    if not eligible:
        return list(resolutions)
    best_index, _ = max(
        eligible, key=lambda item: (_SPECIFICITY[item[1].precision], item[1].confidence, -item[0])
    )
    return [replace(r, is_primary=index == best_index) for index, r in enumerate(resolutions)]
