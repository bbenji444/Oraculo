"""Frases que la IA propone para un concepto «como en Google» (ADR-0109 y ADR-0113).

El analista escribe en sus palabras lo que busca («hackeos a bases de datos
del gobierno»). La IA propone un nombre, frases cortas escritas como titular
(«filtran datos», «hackeo gobierno»), exclusiones y los nombres propios que
escribió la persona («Eternal»). Aquí vive lo que se hace con esa propuesta
antes de mostrarla o buscarla:

- la descripción se valida con los mismos largos que la del concepto;
- cada frase y exclusión pasa por las reglas de una palabra clave
  (``is_searchable_term``); la que no las cumple se descarta en silencio,
  porque la persona solo ve la lista final y la puede editar;
- sin repetidas (sin mayúsculas ni acentos), hasta ``OPEN_MAX_PHRASES``
  frases y ``MAX_SUGGESTED_EXCLUSIONS`` exclusiones;
- una exclusión igual a una frase se quita: se anularían;
- los nombres propios solo cuentan si están tal cual en el texto de la
  persona (``literal_entities``) y no son el lugar de la búsqueda
  (``without_places``), y una frase que no lleva ninguno se descarta:
  «hackean sistemas» no busca a Eternal.

La búsqueda rápida (ADR-0113) busca además el texto **literal** del
analista, como Google (``literal_phrase`` y ``with_literal``): Benji buscó
«Hacker Eternal» y la IA lo volvió «Hackeo Eternal» y trajo 0 notas.

No hace: no llama a la IA ni guarda nada; el analista decide al guardar.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.concept import (
    DESCRIPTION_MAX_LENGTH,
    MAX_REQUIRED_TERMS,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    OPEN_MAX_PHRASES,
    TERM_MIN_LENGTH,
    clean_text,
    is_searchable_term,
)
from app.domain.errors import ConceptValidationError, InvalidRequestError
from app.domain.names import normalize_name
from app.domain.queries import DateWindow, QueryPlace
from app.domain.query_dialects import DIALECTS, GOOGLE_MAX_WORDS

# Menos que esto no alcanza para que la IA proponga las frases de un concepto
# del formulario («robo» a secas): inventaría el resto.
INTENT_MIN_LENGTH = 10
# En la búsqueda rápida se escribe como en Google: «Pemex», «LockBit» o «IA»
# bastan (revisión del 18/11/2026, hallazgo 7). Lo mínimo son las letras o
# números de una palabra clave (``TERM_MIN_LENGTH``), sin espacios ni signos.
QUICK_MIN_USEFUL_CHARS = TERM_MIN_LENGTH
# El literal se busca completo hasta el tope de palabras de Google (antes, 80
# caracteres: «ataques de hackers a la Secretaría de la Defensa Nacional…» se
# quedaba sin literal). Además debe caber con el lugar y las fechas en cada
# proveedor (``literal_fits``).
LITERAL_MAX_WORDS = GOOGLE_MAX_WORDS
# Pocas: cada exclusión puede tirar una nota buena; la IA propone solo las
# que traen basura segura (cursos, publicidad).
MAX_SUGGESTED_EXCLUSIONS = 6
# Una búsqueda rápida nombra uno o dos sujetos («LockBit», «Pemex»); con más,
# la IA está marcando palabras comunes como nombres (ADR-0113). Son los
# términos obligatorios del concepto oculto, así que comparten tope.
MAX_ENTITIES = MAX_REQUIRED_TERMS
DESCRIPTION_FIELD = "description"

# Frases que piden buscar en todo el mundo (ADR-0112), sobre el texto ya
# normalizado (mayúsculas, sin acentos). No incluye «mundial» suelto: «el
# Mundial» es el de futbol.
_WHOLE_WORLD = re.compile(
    r"\b(?:TODO EL MUNDO|EN EL MUNDO|A NIVEL (?:MUNDIAL|GLOBAL|INTERNACIONAL)"
    r"|EN TODO EL PLANETA|EN TODOS LOS PAISES|MUNDIALMENTE|GLOBALMENTE)\b"
)
# Lo que Google lee como orden y no como palabra (ADR-0009): comillas,
# paréntesis y dos puntos. Se cambian por espacios en el literal.
_OPERATOR_CHARS = re.compile(r"[\"“”«»„()\[\]{}:]")
# Operadores de buscador escritos a mano («site:x.com», «when:7d»): se quitan
# completos antes de quitar los dos puntos.
_OPERATOR_TOKEN = re.compile(
    r"^(?:site|intitle|allintitle|inurl|allinurl|intext|filetype|when|after|before"
    r"|sourcecountry|sourcelang):\S*$",
    re.IGNORECASE,
)
# Signos que rodean una palabra y que los buscadores ignoran.
_EDGE_PUNCTUATION = "'‘’`¿?¡!,;…"
# «OR» y «AND» sueltos son operadores en los tres proveedores (ADR-0009);
# ``is_searchable_term`` los rechaza en cualquier mayúscula.
_OPERATOR_WORDS = frozenset({"OR", "AND"})
# Palabras que unen y que solas no nombran nada: no son nombres propios.
_ARTICLES = frozenset({"EL", "LA", "LOS", "LAS"})
_PREPOSITIONS = frozenset({"EN", "DE", "DEL", "DESDE", "PARA", "POR", "A", "AL"})
# «de» o «del» después de una palabra con mayúscula arma un nombre propio
# («Cártel de Sinaloa», «Universidad de Guadalajara»): ese lugar no se quita.
_NAME_PREPOSITIONS = frozenset({"DE", "DEL"})
_CONNECTORS = _ARTICLES | _PREPOSITIONS | {"Y", "E", "O", "U", "CON", "SIN", "SOBRE"}
# Frases de tiempo obvias: las fechas ya se eligen en la consulta. Solo se
# quitan en las orillas del texto, y «hoy» o «ayer» sueltos solo al final:
# al inicio pueden ser un nombre («Hoy No Circula»).
_TIME_CORE = (
    r"(?:HOY|AYER|ESTA SEMANA|ESTE MES|ESTE AÑO|ESTOS DIAS|LA ULTIMA SEMANA|EL ULTIMO MES"
    r"|(?:LOS |LAS )?ULTIM[OA]S? (?:\d+ )?(?:DIAS?|HORAS?|SEMANAS?|MES(?:ES)?))"
)
_TIME_PHRASE = re.compile(rf"(?:(?:DE|DEL|EN|DURANTE|DESDE) )?{_TIME_CORE}")
_LONE_TIME_WORDS = frozenset({"HOY", "AYER"})
# La frase de tiempo más larga que reconoce ``_TIME_PHRASE``: preposición,
# artículo, «últimas», número y unidad («durante las últimas 24 horas»).
_MAX_TIME_WORDS = 5


class EmptySuggestionError(InvalidRequestError):
    """La IA no propuso ninguna frase que se pueda buscar."""

    code = "empty_suggestion"


@dataclass(frozen=True, slots=True)
class SuggestedTerms:
    """Propuesta ya limpia, lista para llenar el formulario.

    Attributes:
        name: Nombre propuesto para el concepto, o ``""`` si no sirvió.
        phrases: Frases tipo titular (hasta ``OPEN_MAX_PHRASES``; al menos
            una, salvo en la búsqueda rápida, que tiene el literal).
        exclude_terms: Exclusiones (hasta ``MAX_SUGGESTED_EXCLUSIONS``).
        entities: Nombres propios, alias, grupos o siglas que escribió la
            persona, con su grafía (``literal_entities``); cada frase lleva
            al menos uno. Vacío si no nombró ninguno (ADR-0113).
    """

    name: str
    phrases: tuple[str, ...]
    exclude_terms: tuple[str, ...]
    entities: tuple[str, ...] = ()


def names_whole_world(text: str) -> bool:
    """Dice si el analista pidió buscar en todo el mundo (ADR-0112).

    La IA solo devuelve lugares del catálogo («en Jalisco»); «en todo el
    mundo» no es un lugar para ella, así que se reconoce aquí, sin pagar.

    Args:
        text: Lo que escribió el analista.

    Returns:
        ``True`` si dice «en todo el mundo», «a nivel mundial», «a nivel
        global» o algo así.

    Example:
        >>> names_whole_world("bases de datos hackeadas en todo el mundo")
        True
        >>> names_whole_world("boletos para el Mundial")
        False
    """
    return _WHOLE_WORLD.search(normalize_name(text)) is not None


def _word(raw: str) -> str:
    """Una palabra sin signos en las orillas; ``""`` si era un operador."""
    word = raw.strip(_EDGE_PUNCTUATION)
    # Punto final de oración, no el de una sigla («S.A.»).
    if word.endswith(".") and word.count(".") == 1:
        word = word[:-1]
    if word.startswith("-") or word.upper() in _OPERATOR_WORDS:
        # «-curso» es una exclusión escrita a mano: buscar «curso» sería lo
        # contrario de lo que se pidió.
        return ""
    return word


def _words(text: str) -> list[str]:
    """Las palabras de un texto como las escribió la persona, sin operadores.

    Args:
        text: Texto libre.

    Returns:
        Las palabras, con sus mayúsculas y acentos.
    """
    tokens = (t for t in clean_text(text).split(" ") if not _OPERATOR_TOKEN.match(t))
    plain = _OPERATOR_CHARS.sub(" ", " ".join(tokens))
    return [w for w in (_word(raw) for raw in plain.split()) if w]


def _norms(text: str) -> list[str]:
    """Las palabras de un texto normalizadas para comparar (sin acentos ni mayúsculas)."""
    return [normalize_name(w) for w in _words(text)]


def _occurrences(haystack: Sequence[str], needle: Sequence[str]) -> list[tuple[int, int]]:
    """Dónde aparecen las palabras de ``needle`` juntas y en orden: ``[(inicio, fin)]``."""
    size = len(needle)
    if not size:
        return []
    return [
        (i, i + size)
        for i in range(len(haystack) - size + 1)
        if list(haystack[i : i + size]) == list(needle)
    ]


def _contains(text: str, term: str) -> bool:
    """Si ``term`` aparece en ``text`` como palabras completas (sin acentos ni mayúsculas)."""
    return bool(_occurrences(_norms(text), _norms(term)))


def _with_preposition(norms: Sequence[str], start: int) -> int:
    """Incluye la preposición (y el artículo) que van antes de una mención.

    «en la Ciudad de México» se quita completo, no solo «Ciudad de México».

    Args:
        norms: Palabras normalizadas del texto.
        start: Dónde empieza la mención.

    Returns:
        El nuevo inicio, o ``start`` si antes no hay una preposición.
    """
    i = start - 1
    while i >= 0 and norms[i] in _ARTICLES:
        i -= 1
    return i if i >= 0 and norms[i] in _PREPOSITIONS else start


class _Literal:
    """Las palabras del texto y cuáles se van quitando (lo usa ``literal_phrase``)."""

    def __init__(self, text: str, entities: Iterable[str]) -> None:
        self.words = _words(text)
        self.norms = [normalize_name(w) for w in self.words]
        self.keep = [True] * len(self.words)
        # Las palabras de un nombre propio nunca se quitan.
        self.protected = {
            i
            for entity in entities
            for start, end in _occurrences(self.norms, _norms(entity))
            for i in range(start, end)
        }

    def drop(self, start: int, end: int) -> bool:
        """Quita las palabras de ``start`` a ``end`` si ninguna es de un nombre propio."""
        if self.protected.intersection(range(start, end)):
            return False
        for i in range(start, end):
            self.keep[i] = False
        return True

    def drop_world(self) -> None:
        """Quita «en todo el mundo», «a nivel mundial»… con su preposición."""
        joined = " ".join(self.norms)
        # Inicio de cada palabra en el texto unido, para traducir la
        # coincidencia del regex a palabras.
        offsets, position = [], 0
        for norm in self.norms:
            offsets.append(position)
            position += len(norm) + 1
        for match in _WHOLE_WORLD.finditer(joined):
            covered = [
                i
                for i, offset in enumerate(offsets)
                if offset < match.end() and offset + len(self.norms[i]) > match.start()
            ]
            if covered:
                self.drop(_with_preposition(self.norms, covered[0]), covered[-1] + 1)

    def drop_place(self, name: str) -> None:
        """Quita cada mención del lugar, salvo la que es parte de un nombre propio."""
        for start, end in _occurrences(self.norms, _norms(name)):
            begin = _with_preposition(self.norms, start)
            if (
                begin < start
                and self.norms[begin] in _NAME_PREPOSITIONS
                and begin > 0
                and self.words[begin - 1][:1].isupper()
            ):
                continue
            self.drop(begin, end)

    def _drop_time_at(self, *, tail: bool) -> bool:
        kept = [i for i, keep in enumerate(self.keep) if keep]
        for size in range(min(_MAX_TIME_WORDS, len(kept)), 0, -1):
            span = kept[-size:] if tail else kept[:size]
            phrase = " ".join(self.norms[i] for i in span)
            lone = size == 1 and phrase in _LONE_TIME_WORDS
            if (
                _TIME_PHRASE.fullmatch(phrase)
                and (tail or not lone)
                and not self.protected.intersection(span)
            ):
                for i in span:
                    self.keep[i] = False
                return True
        return False

    def drop_time(self) -> None:
        """Quita las frases de tiempo de las orillas («de hoy», «últimos 7 días»)."""
        while self._drop_time_at(tail=True):
            pass
        while self._drop_time_at(tail=False):
            pass

    def text(self) -> str:
        """Lo que queda, con las palabras como las escribió la persona."""
        return " ".join(w for w, keep in zip(self.words, self.keep, strict=True) if keep)


def literal_phrase(
    text: str,
    place: str | None,
    *,
    aliases: Sequence[str] = (),
    entities: Iterable[str] = (),
) -> str | None:
    """El texto del analista listo para buscarse tal cual, como en Google (ADR-0113).

    Benji (18/11/2026) buscó «Hacker Eternal» y la IA lo cambió a «Hackeo
    Eternal»: trajo 0 notas, aunque en Google sí había. Lo que escribió la
    persona se busca siempre, con sus palabras, mayúsculas, acentos y orden.
    Solo se le quita lo que ya va aparte en la búsqueda:

    - la mención del lugar que reconoció la búsqueda rápida, con su
      preposición («en Jalisco»), salvo que sea parte de un nombre propio
      («Cártel de Sinaloa», «Universidad de Guadalajara») o de una entidad;
    - «en todo el mundo», «a nivel mundial»… (ADR-0112);
    - frases de tiempo obvias en las orillas («de hoy», «esta semana»,
      «últimos 7 días»): las fechas se eligen en la consulta;
    - comillas, paréntesis, dos puntos y operadores («OR», «-curso»,
      «site:»). La búsqueda exacta entre comillas queda para después.

    Args:
        text: Lo que escribió el analista.
        place: Lugar que reconoció la búsqueda rápida («Jalisco»), o ``None``.
        aliases: Otros nombres de ese lugar en el catálogo («CDMX»).
        entities: Nombres propios del texto (``literal_entities``): sus
            palabras nunca se quitan.

    Returns:
        El literal, o ``None`` si no queda nada o no cumple las reglas de una
        palabra clave, con el tope de palabras de Google en lugar del de
        caracteres (``is_searchable_term`` con ``LITERAL_MAX_WORDS``).

    Example:
        >>> literal_phrase("Robo de autos en Jalisco", "Jalisco")
        'Robo de autos'
        >>> literal_phrase("Cártel de Sinaloa", "Sinaloa")
        'Cártel de Sinaloa'
    """
    literal = _Literal(text, entities)
    literal.drop_world()
    for name in (place, *aliases) if place else ():
        literal.drop_place(name)
    literal.drop_time()
    phrase = literal.text()
    return phrase if phrase and is_searchable_term(phrase, max_words=LITERAL_MAX_WORDS) else None


def literal_fits(
    literal: str, place: QueryPlace, exclusions: Sequence[str], window: DateWindow
) -> bool:
    """Dice si el literal cabe, solo, en una consulta de cada proveedor.

    Un literal de hasta ``LITERAL_MAX_WORDS`` palabras más el lugar, las
    exclusiones y el sufijo de fechas («when:7d») puede pasar del límite;
    entonces ``build_queries`` rechazaría la búsqueda entera
    (``QueryTooLongError``). Se revisa con y sin comillas, lo más largo.

    Args:
        literal: El texto del analista (``literal_phrase``).
        place: Cómo se nombra el lugar en la consulta (``place_for``).
        exclusions: Exclusiones del concepto.
        window: Rango de fechas.

    Returns:
        ``True`` si cabe en todos los proveedores.

    Example:
        >>> literal_fits("robo de autos", jalisco, ("curso",), DateWindow.last_days(7, hoy))
        True
    """
    return all(
        dialect.fits(dialect.render((literal,), place, exclusions, window, exact=exact))
        for dialect in DIALECTS.values()
        for exact in (True, False)
    )


def literal_entities(text: str, proposed: Iterable[str]) -> tuple[str, ...]:
    """Los nombres propios que dio la IA y que de verdad escribió la persona.

    La IA puede «corregir» («Hackeo» por «hacker») o inventar. Solo se acepta
    un nombre cuyas palabras aparecen juntas y en orden en el texto (sin
    mayúsculas ni acentos), y se devuelve con la grafía de la persona.

    Args:
        text: Lo que escribió el analista.
        proposed: Entidades que propuso la IA.

    Returns:
        Hasta ``MAX_ENTITIES`` entidades, sin repetir, en el orden de la IA.

    Example:
        >>> literal_entities("hacker eternal", ["Eternal", "Hackeo"])
        ('eternal',)
    """
    words = _words(text)
    norms = [normalize_name(w) for w in words]
    found: list[str] = []
    seen: set[str] = set()
    for value in proposed:
        needle = _norms(value)
        places = _occurrences(norms, needle)
        if not places or set(needle) <= _CONNECTORS:
            continue
        start, end = places[0]
        entity = " ".join(words[start:end])
        norm = normalize_name(entity)
        if norm in seen or not is_searchable_term(entity):
            continue
        seen.add(norm)
        found.append(entity)
        if len(found) == MAX_ENTITIES:
            break
    return tuple(found)


def without_places(entities: Sequence[str], place_names: Iterable[str | None]) -> tuple[str, ...]:
    """Quita de los nombres propios los que son el lugar de la búsqueda.

    Revisión del 18/11/2026 (hallazgo 3): si la IA pone «Jalisco» en
    entities, el lugar quedaba protegido en el literal, se descartaban todas
    las frases de la IA (ninguna lleva «Jalisco») y el juez exigía «Debe
    hablar de: Jalisco». Un lugar ya va aparte, en la región de la búsqueda.

    Args:
        entities: Nombres propios ya validados (``literal_entities``).
        place_names: El lugar con todos sus nombres: el que dio la IA, su
            estado, y los del catálogo (nombre, alias, términos de búsqueda,
            estado y país). Los vacíos se ignoran.

    Returns:
        Las entidades que no son ninguno de esos nombres (sin mayúsculas ni
        acentos), en su orden. Un nombre propio que solo lleva el lugar
        («Cártel de Sinaloa») se queda.

    Example:
        >>> without_places(("Jalisco", "CJNG"), ["Jalisco", None])
        ('CJNG',)
    """
    names = {normalize_name(n) for n in place_names if n and n.strip()}
    return tuple(e for e in entities if normalize_name(e) not in names)


def with_literal(
    literal: str | None, phrases: Sequence[str], exclude_terms: Sequence[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Pone el literal primero y deja las frases de la IA después (ADR-0113).

    Args:
        literal: El texto del analista (``literal_phrase``), o ``None``.
        phrases: Frases de la IA ya limpias.
        exclude_terms: Exclusiones de la IA ya limpias.

    Returns:
        ``(palabras clave, exclusiones)``: el literal y luego las frases que
        no lo repiten (sin mayúsculas ni acentos), hasta ``OPEN_MAX_PHRASES``.
        Se quita la exclusión que esté dentro del literal: la persona pidió
        esas palabras y se anularían.

    Example:
        >>> with_literal("hacker eternal", ["Hacker Eternal", "Eternal filtra"], ["curso"])
        (('hacker eternal', 'Eternal filtra'), ('curso',))
    """
    if literal is None:
        return tuple(phrases), tuple(exclude_terms)
    norm = normalize_name(literal)
    others = [p for p in phrases if normalize_name(p) != norm]
    keywords = (literal, *others)[:OPEN_MAX_PHRASES]
    exclusions = tuple(e for e in exclude_terms if not _contains(literal, e))
    return keywords, exclusions


def _quick_intent_error() -> ConceptValidationError:
    return ConceptValidationError(
        "Escribe lo que buscas, como en Google.",
        {
            "problemas": [
                {
                    "campo": DESCRIPTION_FIELD,
                    "mensaje": (
                        f"Escribe al menos {QUICK_MIN_USEFUL_CHARS} letras o números y hasta "
                        f"{DESCRIPTION_MAX_LENGTH} caracteres; por ejemplo «Pemex» o "
                        "«robo de autos en Jalisco»."
                    ),
                }
            ]
        },
    )


def validated_intent(description: str, *, quick: bool = False) -> str:
    """Limpia y valida lo que el analista escribió.

    Args:
        description: Lo que busca, en sus palabras.
        quick: ``True`` en la búsqueda rápida: basta un nombre («Pemex»),
            con al menos ``QUICK_MIN_USEFUL_CHARS`` letras o números. En el
            formulario de conceptos se piden ``INTENT_MIN_LENGTH`` caracteres.

    Returns:
        El texto sin espacios repetidos.

    Raises:
        ConceptValidationError: Si es muy corto o muy largo, con el campo
            ``description`` como en el formulario.
    """
    intent = clean_text(description)
    if quick:
        useful = sum(1 for char in intent if char.isalnum())
        if useful < QUICK_MIN_USEFUL_CHARS or len(intent) > DESCRIPTION_MAX_LENGTH:
            raise _quick_intent_error()
        return intent
    if not INTENT_MIN_LENGTH <= len(intent) <= DESCRIPTION_MAX_LENGTH:
        raise ConceptValidationError(
            "Describe en tus palabras lo que buscas para que la IA proponga las frases.",
            {
                "problemas": [
                    {
                        "campo": DESCRIPTION_FIELD,
                        "mensaje": (
                            f"Escribe entre {INTENT_MIN_LENGTH} y {DESCRIPTION_MAX_LENGTH} "
                            "caracteres; por ejemplo «hackeos a bases de datos del gobierno»."
                        ),
                    }
                ]
            },
        )
    return intent


def _unique_terms(raw: Iterable[str], limit: int, taken: set[str]) -> tuple[str, ...]:
    """Términos válidos y sin repetir, en orden, hasta ``limit``."""
    kept: list[str] = []
    for value in raw:
        term = clean_text(value)
        norm = normalize_name(term)
        if not term or norm in taken or not is_searchable_term(term):
            continue
        taken.add(norm)
        kept.append(term)
        if len(kept) == limit:
            break
    return tuple(kept)


def clean_suggestion(
    name: str,
    phrases: Iterable[str],
    exclude_terms: Iterable[str],
    *,
    entities: Sequence[str] = (),
    require_phrases: bool = True,
) -> SuggestedTerms:
    """Aplica las reglas del concepto a lo que respondió la IA.

    Args:
        name: Nombre que propuso.
        phrases: Frases que propuso, en su orden (las primeras son las mejores).
        exclude_terms: Exclusiones que propuso.
        entities: Nombres propios ya validados contra el texto
            (``literal_entities``). Si hay, una frase que no lleve ninguno se
            descarta: «hackean sistemas» no busca a Eternal (ADR-0113).
        require_phrases: ``False`` en la búsqueda rápida: aunque no quede
            ninguna frase de la IA, se busca el literal del analista.

    Returns:
        La propuesta limpia.

    Raises:
        EmptySuggestionError: Si no quedó ninguna frase que se pueda buscar y
            ``require_phrases`` es ``True``.

    Example:
        >>> clean_suggestion("Hackeos", ["filtran datos", "Filtran datos", "a OR b"], ["curso"])
        SuggestedTerms(name='Hackeos', phrases=('filtran datos',),
                       exclude_terms=('curso',), entities=())
    """
    candidates = (
        [p for p in phrases if any(_contains(p, entity) for entity in entities)]
        if entities
        else list(phrases)
    )
    taken: set[str] = set()
    kept_phrases = _unique_terms(candidates, OPEN_MAX_PHRASES, taken)
    if not kept_phrases and require_phrases:
        raise EmptySuggestionError(
            "La IA no propuso frases que se puedan buscar. Escríbelo con otras palabras "
            "o agrega las frases a mano."
        )
    kept_exclusions = _unique_terms(exclude_terms, MAX_SUGGESTED_EXCLUSIONS, taken)
    clean_name = clean_text(name)
    if not NAME_MIN_LENGTH <= len(clean_name) <= NAME_MAX_LENGTH:
        clean_name = ""
    return SuggestedTerms(clean_name, kept_phrases, kept_exclusions, tuple(entities))
