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
- El estado que da la IA manda: un homónimo de otro estado nunca gana
  ("Polanco, CDMX" caía en una localidad de Jalisco; 20/10/2026). Si no se
  encuentra el lugar dentro de ese estado, la nota se ubica en el estado.
- Palabras genéricas al inicio ("alcaldía", "colonia", "calle") se quitan
  antes de buscar: INEGI guarda "Miguel Hidalgo", no "alcaldía Miguel Hidalgo".
- Lo que INEGI no tiene (colonias, barrios) se busca en las colonias de
  OpenStreetMap, siempre dentro del estado de la nota (ADR-0020). Si todas las
  coincidencias caen en un solo municipio, la nota se pinta en la colonia.

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
# Colonias de OpenStreetMap (ADR-0020): un poco menos que INEGI porque los
# nombres son de voluntarios; exacta ("Roma Norte") o como familia ("Polanco"
# junta "Polanco 1ª Sección", "Polanco III Sección"...).
NEIGHBORHOOD_EXACT_CONFIDENCE = 0.85
NEIGHBORHOOD_FAMILY_CONFIDENCE = 0.75
# Preferencia entre tipos de lugar de OpenStreetMap con el mismo nombre.
_NEIGHBORHOOD_KIND_ORDER = ("neighbourhood", "macrohood", "locality")
# "Solo sabemos el estado que dice la IA": alcanza justo el umbral para ser la
# ubicación principal si no hay nada más preciso (se pinta con anillo punteado).
STATE_HINT_CONFIDENCE = DEFAULT_MIN_CONFIDENCE
# Palabras genéricas que la IA deja al inicio de una mención (medido en el
# historial del 20/10/2026: 51 de 140 menciones sin resolver las traían). Ya
# normalizadas; de la más larga a la más corta para quitar la más específica.
# "ESTADO DE" no está: "Estado de México" es un alias del estado 15.
GENERIC_PREFIXES = (
    "UNIDAD HABITACIONAL ",
    "FRACCIONAMIENTO ",
    "MUNICIPIO DE ",
    "DELEGACION ",
    "BARRIO DE ",
    "CARRETERA ",
    "BOULEVARD ",
    "MUNICIPIO ",
    "ALCALDIA ",
    "COLONIA ",
    "AVENIDA ",
    "BULEVAR ",
    "CALZADA ",
    "BARRIO ",
    "FRACC. ",
    "PUEBLO ",
    "CALLE ",
    "BLVD. ",
    "FRACC ",
    "BLVD ",
    "COL. ",
    "AV. ",
    "COL ",
    "AV ",
)
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


def strip_generic_prefix(name_norm: str) -> str:
    """Quita una palabra genérica del inicio de un nombre ya normalizado.

    Args:
        name_norm: Nombre normalizado (``normalize_name``).

    Returns:
        El nombre sin la palabra; el mismo si no la tenía.

    Example:
        >>> strip_generic_prefix("ALCALDIA MIGUEL HIDALGO")
        'MIGUEL HIDALGO'
    """
    for prefix in GENERIC_PREFIXES:
        if name_norm.startswith(prefix):
            return name_norm[len(prefix) :].strip()
    return name_norm


# Artículos con que los medios nombran municipios que INEGI registra sin
# ellos ("El Rosario" → "Rosario", "La Concordia" → "Concordia"; Sinaloa,
# búsqueda real del 19/10/2026). Solo se prueban si el nombre completo no está.
LEADING_ARTICLES = ("LOS ", "LAS ", "EL ", "LA ")


def strip_leading_article(name_norm: str) -> str:
    """Quita un artículo del inicio de un nombre normalizado.

    Args:
        name_norm: Nombre normalizado.

    Returns:
        El nombre sin el artículo; el mismo si no lo tenía.

    Example:
        >>> strip_leading_article("EL ROSARIO")
        'ROSARIO'
    """
    for article in LEADING_ARTICLES:
        if name_norm.startswith(article):
            return name_norm[len(article) :].strip()
    return name_norm


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
        detail: Lugar más fino dentro de la región, si se usó uno ("Colonia
            Polanco"): entonces el punto es el de ese lugar, no el centroide.
    """

    region_id: int
    code: str
    level: RegionLevel
    name: str
    display_name: str
    country_code: str
    lon: float
    lat: float
    detail: str | None = None

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
        municipality_hint: Municipio o alcaldía que sugiere la IA para una
            colonia o calle ("Miguel Hidalgo"; prompt ``enrich_v2``).
    """

    text: str
    role: MentionRole
    kind_hint: RegionLevel | None = None
    state_hint: str | None = None
    country: str | None = None
    municipality_hint: str | None = None

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


@dataclass(frozen=True, slots=True)
class Neighborhood:
    """Una colonia, barrio o zona de OpenStreetMap (tabla ``places``).

    Attributes:
        name: Nombre original ("Colonia Polanco 1ª Sección").
        name_core: Nombre normalizado sin la palabra genérica ("POLANCO 1ª SECCION").
        kind: ``neighbourhood``, ``macrohood`` o ``locality``.
        municipality: Municipio de INEGI que la contiene.
        lon: Longitud de su punto.
        lat: Latitud de su punto.
    """

    name: str
    name_core: str
    kind: str
    municipality: Place
    lon: float
    lat: float


def choose_neighborhood(
    name_core: str, matches: Sequence[Neighborhood], municipality_code: str | None = None
) -> tuple[Place, float] | None:
    """Elige la colonia de OpenStreetMap de una mención (ADR-0020).

    Se prefieren las de nombre exacto; si no hay, las de la misma familia
    ("Polanco" → "Polanco 1ª Sección"...). Con municipio sugerido por la IA,
    solo cuentan las de ese municipio: "Ajusco, Tlalpan" no es la Colonia
    Ajusco de Coyoacán (historial del 20/10/2026). Solo se acepta si todas las
    que quedan caen en **un** municipio: "Colonia Centro" existe en cientos y
    no dice nada.

    Args:
        name_core: Mención normalizada, sin palabra genérica.
        matches: Colonias del estado de la nota con ese nombre o familia.
        municipality_code: Clave INEGI del municipio que sugiere la IA, si hay.

    Returns:
        El municipio con el punto y el nombre de la colonia, y la confianza; o
        ``None`` si no hay o es ambigua.

    Example:
        >>> choose_neighborhood("ROMA NORTE", [roma_norte])
        (Place(..., detail="Colonia Roma Norte"), 0.85)
    """
    pool = list(matches)
    if municipality_code is not None:
        pool = [m for m in pool if m.municipality.code == municipality_code]
    exact = [m for m in pool if m.name_core == name_core]
    chosen = exact or pool
    if not chosen or len({m.municipality.region_id for m in chosen}) != 1:
        return None
    best = min(
        chosen,
        key=lambda m: (
            _NEIGHBORHOOD_KIND_ORDER.index(m.kind) if m.kind in _NEIGHBORHOOD_KIND_ORDER else 9,
            len(m.name_core),
        ),
    )
    place = replace(best.municipality, lon=best.lon, lat=best.lat, detail=best.name)
    confidence = NEIGHBORHOOD_EXACT_CONFIDENCE if exact else NEIGHBORHOOD_FAMILY_CONFIDENCE
    return place, confidence


def seat_area(searched: Place, municipality: Place | None) -> Place:
    """Zona real de una búsqueda: la localidad cabecera homónima vale por su municipio.

    En la CDMX cada alcaldía tiene una localidad urbana con su mismo nombre que
    cubre casi toda la alcaldía (090160001 "Miguel Hidalgo" dentro de 09016).
    Ni las notas ni las personas las distinguen: una búsqueda en esa localidad
    marcaba "fuera de la región" todo lo ubicado en la alcaldía o sus colonias
    (búsqueda real del 20/10/2026: 0 notas dentro).

    Args:
        searched: Región elegida para la búsqueda.
        municipality: Su municipio, si es una localidad.

    Returns:
        El municipio si la búsqueda es su localidad cabecera con el mismo nombre;
        si no, la misma región.
    """
    if (
        searched.level is RegionLevel.LOCALITY
        and municipality is not None
        and municipality.level is RegionLevel.MUNICIPALITY
        and searched.code.startswith(municipality.code)
        and normalize_name(searched.name) == normalize_name(municipality.name)
    ):
        return municipality
    return searched


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
        context_states: Claves de estado que nombra la misma nota. Si hay,
            las localidades fuera de esos estados se descartan.
        searched: Región de la búsqueda, si la hay.

    Returns:
        La elegida con su confianza; o solo el estado común; o nada.
    """
    states = set(context_states)
    if states:
        # Hay cerca de 300 mil localidades y muchas se llaman como colonias o
        # barrios ("colonia La Gloria" de Juchitán coincidía con un pueblo de
        # Guanajuato; búsqueda real del 17/10/2026). Si la nota nombra sus
        # estados, una localidad fuera de todos ellos es casi siempre un
        # homónimo: mejor sin ubicar que en el lugar equivocado (§11). Los
        # municipios sí se conservan: una nota puede mencionar uno de otro
        # estado sin nombrar ese estado.
        candidates = [
            c for c in candidates if c.level is not RegionLevel.LOCALITY or c.state_code in states
        ]
    if not candidates:
        return Choice(None, None, UNKNOWN_CONFIDENCE)
    if len(candidates) == 1:
        return Choice(candidates[0], None, EXACT_CONFIDENCE)
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


def _inside(resolution: Resolution, searched: Place | None) -> bool:
    place = resolution.place
    if searched is None or place is None:
        return False
    return place.region_id == searched.region_id or searched.contains(place)


def mark_primary(
    resolutions: Sequence[Resolution], min_confidence: float, searched: Place | None = None
) -> list[Resolution]:
    """Marca la ubicación principal de una nota (paso 6 de §11).

    1. Entre los lugares del hecho con confianza suficiente, se prefieren los
       que caen dentro de la región buscada; de ellos, el más específico.
    2. Si la IA no marcó ningún lugar del hecho utilizable, se usa el lugar
       *mencionado* más específico dentro de la región buscada (13 de las 24
       notas sin ubicación del historial del 20/10/2026 eran así). Conserva su
       papel "mencionado" para que la ficha lo diga.

    Args:
        resolutions: Menciones resueltas de una nota.
        min_confidence: Umbral (``GEO_MIN_CONFIDENCE``).
        searched: Región de la búsqueda, si la hay.

    Returns:
        Las mismas resoluciones, con a lo más una ``is_primary``. Si ninguna
        califica, la nota queda "sin ubicación" y no se pinta en el mapa.
    """
    confident = [
        (index, r)
        for index, r in enumerate(resolutions)
        if r.place is not None and r.confidence >= min_confidence
    ]
    events = [(i, r) for i, r in confident if r.mention.role is MentionRole.EVENT]
    events_inside = [(i, r) for i, r in events if _inside(r, searched)]
    mentioned_inside = [
        (i, r)
        for i, r in confident
        if r.mention.role is MentionRole.MENTIONED and _inside(r, searched)
    ]
    eligible = events_inside or events or mentioned_inside
    if not eligible:
        return list(resolutions)
    best_index, _ = max(
        eligible, key=lambda item: (_SPECIFICITY[item[1].precision], item[1].confidence, -item[0])
    )
    return [replace(r, is_primary=index == best_index) for index, r in enumerate(resolutions)]
