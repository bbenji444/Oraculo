"""Filtro de palabras del pedido, antes de pagarle a la IA (ADR-0114).

Benji (18/11/2026) comparó con Google y vio que, en las búsquedas rápidas y
los conceptos «como en Google», las relevantes no hablaban de lo pedido y
«No relevantes» era basura total. Medido en la VM: «roban vehículos
Jalisco» trajo «Concentración feminista en Guadalajara», y «eternal hacker»
trajo 12 «relevantes» de otros hackeos, ninguna con Eternal. Nada las cortaba
antes de la IA: el único filtro de palabras era el de las subdivisiones
(``TopicMatcher``, ADR-0038).

Aquí se decide, sin IA y sin costo, si el título o el fragmento de una nota
hablan de lo pedido. Lo que se exige depende de **cómo llegó** la nota
(``QueryOrigin``, una por nota):

- **Texto completo** (``QueryOrigin.full_text``: Google News RSS, SearchApi
  Google News y los resultados orgánicos de Google web). Ese buscador ya
  exigió las palabras de la consulta en el texto de la nota, así que **no se
  mira el tema**: decide el juez, y la banda «ajena» esconde en pantalla lo
  que no sirva. Solo cuenta la entidad, con la excepción por procedencia de
  abajo.
- **Carrusel de Google web** (``QueryOrigin.carousel``: videos, shorts,
  tweets, noticias destacadas, perspectivas y foros). Google no los busca en
  el texto completo y casi nunca traen fragmento: si el concepto tiene
  entidad, la nota la tiene que nombrar en el título, el fragmento o el
  canal o autor (``source``); si la nombra, pasa aunque no traiga la raíz del
  tema. Sin entidad que exigir, se pide el tema.
- **Lo demás** (índice local, GDELT, BrowserWork): tema y entidad en el
  título o el fragmento.

Las dos reglas:

- **Entidad (estricta).** Si el concepto tiene términos obligatorios
  («Eternal», ADR-0113), la nota debe nombrar cada uno como palabra
  completa. Un nombre de persona de dos o tres palabras también cuenta con
  su última palabra, y uno de tres palabras de contenido o más con su
  sigla (``term_aliases``): «Harfuch» nombra a «Omar García Harfuch» y
  «FGR» a la «Fiscalía General de la República». Hay una excepción por
  **procedencia**: si la trajo una consulta
  que llevaba ese término en un buscador de texto completo, ese buscador ya
  encontró la palabra en algún lado de la nota, aunque no en el título. La
  nota pasa marcada como «entidad sin confirmar en el título» y el juez lo
  sabe. Así se salvan las 6 notas del Buró Laboral, que Google News trajo
  por «hacker eternal» y cuyo título no dice «Eternal».
- **Tema (laxa).** Al menos una raíz del tema en el título o el fragmento.
  Las raíces salen de las palabras de contenido de lo que escribió el
  analista y de las frases del concepto (el literal y las de la IA), sin
  palabras vacías, sin el lugar y sin las entidades. Si el analista solo
  escribió un nombre («LockBit»), no hay tema que exigir y no se filtra por
  tema: la entidad es todo el pedido.

**Raíces.** Es un recorte de terminaciones del español hecho a mano, en dos
pasos: primero el plural y después una terminación de verbo o de género.
Dos palabras empatan si quedan **iguales** después del recorte, no si una
empieza con la otra:

- «robo», «roban» y «robaron» quedan en ROB, pero «Roberto» queda en ROBERT
  y «robot» en ROBOT;
- «autos» queda en AUT y «autoridad» en AUTORIDAD;
- «hacker», «hackeo», «hackean» y «hackeadas» quedan en HACK.

El recorte **no** junta todas las formas de una palabra: «desapariciones»
queda en DESAPARI y «desaparecidos» en DESAPAREC; «huachicoleros» en
HUACHICOLER y «huachicol» en HUACHICOL; «ataque» y «atacan», «violencia» y
«violento» tampoco empatan, y un sinónimo («hidrocarburo» por «huachicol»)
nunca. Cuando falla, **tira** una nota del tema antes de que la vea la IA
(revisión del 18/11/2026, títulos reales). Por eso el tema solo se exige
donde el buscador no exigió ya las palabras: en el índice local, GDELT,
BrowserWork y los carruseles. No se usa un stemmer de librería porque sería
una dependencia nueva (CLAUDE.md §3) y el dominio no importa librerías
(§6.1).

Quién lo usa: ``plan_queries`` arma un ``CoreTerms`` por concepto abierto y
lo cuelga de sus consultas; ``RunSearch`` filtra con ``CoreMatcher`` y le
avisa al juez qué entidades no están en el título (``missing_terms``).

No hace: no aplica a los conceptos exactos ni al monitor FGR (sus consultas
no llevan ``CoreTerms``), no consulta la base y no llama a la IA.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.names import normalize_name

# Lo mínimo que debe quedar de una palabra después del recorte. Con 2 letras
# «red» quedaría en RE y empataría «reto» o «rey»; con 3, «robo» → ROB y
# «dato» → DAT, que son las raíces que se buscan.
MIN_STEM_LENGTH = 3
# Palabras más cortas no dicen el tema (artículos, preposiciones, «IA»
# suelta). Las siglas de 3 letras («FGR», «SAT») sí cuentan.
MIN_ROOT_WORD_LENGTH = 3
# Un nombre de persona sale en los títulos casi siempre solo con su apellido
# («Harfuch confirma la captura de El Topo»). Prueba real del 18/11/2026:
# exigir «Omar García Harfuch» completo dejó 40 notas «por confirmar», con
# la pista falsa de que el título no lo nombraba, y tiró 44 antes de la IA.
# Con 5 letras o más el apellido no es una palabra corta común («Paz»,
# «Gil»): esos nombres se siguen exigiendo completos.
MIN_SURNAME_LENGTH = 5
# Nombre y apellido, cuando menos: una sola palabra («Eternal») ya es todo.
MIN_NAME_WORDS = 2
# Nombre y dos apellidos, cuando más. Con cuatro palabras la última ya no es
# seguro que sea un apellido: «Generación» de «Cártel Jalisco Nueva
# Generación» es una palabra común. Esos cuentan completos o con su sigla.
MAX_NAME_WORDS = 3
# Los títulos nombran a las instituciones por su sigla («FGR asegura 2
# predios»). Prueba real del 18/11/2026: exigir «Fiscalía General de la
# República» completo tiró 90 notas antes de la IA. Una sigla de 2 letras
# («CS» de «Cártel de Sinaloa») diría otra cosa; con 3 o más es propia.
MIN_ACRONYM_LENGTH = 3
# Plurales, en este orden: «camiones» → CAMION, «datos» → DATO.
_PLURALS = ("ES", "S")
# Terminaciones de verbo, género y derivación que se recortan después del
# plural, de la más larga a la más corta (gana la más larga). La familia
# -EAR va completa porque así se conjugan los verbos tomados del inglés
# («hackear», «hackean», «hackeado»). No incluye -OR/-ORES ni -AD: con ellas
# «autores» y «autoridad» quedarían en AUT, igual que «autos».
_ENDINGS = tuple(
    sorted(
        {
            "IERON",
            "EARON",
            "ARON",
            "IENDO",
            "EANDO",
            "ANDO",
            "ACION",
            "CION",
            "ADORA",
            "ADOR",
            "EADO",
            "EADA",
            "ABAN",
            "AMOS",
            "ADO",
            "ADA",
            "IDO",
            "IDA",
            "ABA",
            "EAN",
            "EAR",
            "IAN",
            "AN",
            "EN",
            "AR",
            "ER",
            "IR",
            "EA",
            "EO",
            "A",
            "O",
            "E",
        },
        key=len,
        reverse=True,
    )
)
# Palabras de enlace: artículos, preposiciones y conjunciones. Unen las
# palabras de un nombre («Fiscalía General de la República») y no dan letra
# a su sigla. Ya normalizadas (mayúsculas, sin acentos); las de menos de
# ``MIN_ROOT_WORD_LENGTH`` letras («DE», «Y») ni hace falta listarlas.
CONNECTORS = frozenset(
    {
        # Artículos y contracciones.
        "EL",
        "LA",
        "LOS",
        "LAS",
        "LO",
        "UN",
        "UNA",
        "UNOS",
        "UNAS",
        "AL",
        "DEL",
        # Preposiciones.
        "ANTE",
        "BAJO",
        "CON",
        "CONTRA",
        "DESDE",
        "DURANTE",
        "ENTRE",
        "HACIA",
        "HASTA",
        "MEDIANTE",
        "PARA",
        "POR",
        "SEGUN",
        "SIN",
        "SOBRE",
        "TRAS",
        # Conjunciones y relativos.
        "QUE",
        "PERO",
        "SINO",
        "PORQUE",
        "COMO",
        "CUANDO",
        "DONDE",
        "QUIEN",
        "QUIENES",
        "CUAL",
        "CUALES",
    }
)
# Palabras que no dicen de qué trata la nota: las de enlace, pronombres,
# verbos auxiliares, cantidades, tiempo y las de «en todo el mundo»
# (ADR-0112). «Nueva» está aquí por el tiempo, pero sí da letra a la sigla
# («CJNG»): por eso la sigla usa solo ``CONNECTORS``.
STOPWORDS = CONNECTORS | frozenset(
    {
        # Pronombres y posesivos.
        "SUS",
        "LES",
        "NOS",
        "MIS",
        "TUS",
        "ESTE",
        "ESTA",
        "ESTOS",
        "ESTAS",
        "ESTO",
        "ESE",
        "ESA",
        "ESOS",
        "ESAS",
        "ESO",
        "AQUEL",
        "ELLA",
        "ELLOS",
        "ELLAS",
        # Verbos auxiliares.
        "SON",
        "FUE",
        "FUERON",
        "SER",
        "ESTAN",
        "HAY",
        "HAN",
        "HABER",
        "TIENE",
        "TIENEN",
        # Cantidades y adverbios.
        "MAS",
        "MENOS",
        "MUY",
        "TODO",
        "TODOS",
        "TODA",
        "TODAS",
        "OTRO",
        "OTRA",
        "OTROS",
        "OTRAS",
        "MISMO",
        "MISMA",
        "TAMBIEN",
        "CASI",
        # Tiempo: las fechas ya van en la consulta.
        "HOY",
        "AYER",
        "DIA",
        "DIAS",
        "SEMANA",
        "SEMANAS",
        "MES",
        "MESES",
        "AÑO",
        "AÑOS",
        "HORA",
        "HORAS",
        "ULTIMO",
        "ULTIMA",
        "ULTIMOS",
        "ULTIMAS",
        "RECIENTE",
        "RECIENTES",
        # «En todo el mundo», «a nivel global» (ADR-0112): son el lugar.
        "MUNDO",
        "PLANETA",
        "NIVEL",
        "GLOBAL",
        "PAIS",
        "PAISES",
        # Palabras de buscador que no son tema.
        "NOTICIA",
        "NOTICIAS",
        "NOTA",
        "NOTAS",
        "CASO",
        "CASOS",
        "NUEVO",
        "NUEVA",
        "NUEVOS",
        "NUEVAS",
    }
)
_WORD = re.compile(r"\w+")
# Llave de ``RawArticle.raw`` donde el adaptador de Google web
# (``searchapi_web.SECTIONS``) deja la sección de la respuesta.
RAW_SECTION_KEY = "section"
# Resultados orgánicos de Google web: Google exige las palabras en el texto
# completo de la página, como Google News (ADR-0115).
WEB_ORGANIC_SECTION = "organic_results"
# Carruseles de Google web, con su nombre para el juez. No se buscan en el
# texto completo (el video de La Saga sobre Eternal no dice «hacker» y el de
# UnoTV, genérico, no dice «Eternal»: fixture real del 18/11/2026). Una
# prueba revisa que sean los del adaptador.
WEB_SECTION_LABELS: dict[str, str] = {
    "inline_videos": "videos",
    "inline_shorts": "videos cortos",
    "inline_tweets": "publicaciones de X",
    "top_stories": "noticias destacadas",
    "discussions_and_forums": "foros",
    "perspectives": "perspectivas",
}
# Contexto de la entidad para el juez (revisión del 18/11/2026, hallazgo 4):
# lo que dicen de ella otras notas de la misma búsqueda que sí la nombran.
# Con 6 caben los 2 o 3 hechos que una entidad suele tener en una semana
# (Eternal: Buró Laboral, Pillofon, IMSS) aunque varios medios repitan uno.
MAX_CONTEXT_FRAGMENTS = 6
# Un título largo de Google News (~120 caracteres) más el inicio de su
# fragmento. Con 6 fragmentos son ~1,300 caracteres (~350 tokens) más por
# nota sin confirmar.
MAX_CONTEXT_CHARS = 220
# Une el título con su fragmento y marca un fragmento recortado.
_CONTEXT_JOIN = " — "
_ELLIPSIS = "…"


def _text_norm(title: str, snippet: str | None) -> str:
    """Título y fragmento normalizados: la fórmula de ``news_index.index_text_norm``.

    No se importa de ahí porque ``news_index`` depende de ``queries``, que
    depende de este módulo (``PlannedQuery.core``). Una prueba revisa que las
    dos digan lo mismo.
    """
    return normalize_name(f"{title} {snippet or ''}")


def stem(word: str) -> str:
    """Recorta una palabra ya normalizada a su raíz (plural y terminación).

    Args:
        word: Palabra normalizada (``normalize_name``: mayúsculas, sin acentos).

    Returns:
        La raíz. Si recortar dejaría menos de ``MIN_STEM_LENGTH`` letras, esa
        terminación no se recorta.

    Example:
        >>> [stem(w) for w in ("ROBO", "ROBAN", "ROBARON", "ROBERTO", "ROBOT")]
        ['ROB', 'ROB', 'ROB', 'ROBERT', 'ROBOT']
        >>> [stem(w) for w in ("AUTOS", "AUTORIDAD", "HACKER", "HACKEADAS")]
        ['AUT', 'AUTORIDAD', 'HACK', 'HACK']
    """
    for plural in _PLURALS:
        if word.endswith(plural) and len(word) - len(plural) >= MIN_STEM_LENGTH:
            word = word[: -len(plural)]
            break
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= MIN_STEM_LENGTH:
            return word[: -len(ending)]
    return word


def _words(text: str) -> list[str]:
    """Las palabras de un texto, normalizadas."""
    return _WORD.findall(normalize_name(text))


def theme_roots(texts: Iterable[str], excluded: Iterable[str] = ()) -> tuple[str, ...]:
    """Raíces de las palabras de contenido de unos textos.

    Args:
        texts: Lo que escribió el analista y las frases del concepto.
        excluded: Términos cuyas palabras no son tema: el lugar y las
            entidades («Jalisco», «Eternal»).

    Returns:
        Raíces sin repetir, en orden de aparición. Quedan fuera las palabras
        vacías (``STOPWORDS``), las de menos de ``MIN_ROOT_WORD_LENGTH``
        letras, los números y las palabras de ``excluded``.

    Example:
        >>> theme_roots(["robo de vehículos en Jalisco"], ["Jalisco"])
        ('ROB', 'VEHICUL')
    """
    skip = {word for term in excluded for word in _words(term)}
    roots: dict[str, None] = {}
    for text in texts:
        for word in _words(text):
            if (
                len(word) < MIN_ROOT_WORD_LENGTH
                or word.isdigit()
                or word in STOPWORDS
                or word in skip
            ):
                continue
            roots[stem(word)] = None
    return tuple(roots)


@dataclass(frozen=True, slots=True)
class CoreTerms:
    """Lo que una nota debe nombrar para pasar al juez (un concepto abierto).

    Attributes:
        required: Términos obligatorios tal como los escribió el analista
            («Eternal»); cada uno debe aparecer completo.
        roots: Raíces del tema (``theme_roots``); basta una. Vacío = no se
            filtra por tema.
    """

    required: tuple[str, ...]
    roots: tuple[str, ...]


def core_terms_for(
    description: str,
    keywords: Sequence[str],
    required_terms: Sequence[str],
    place_names: Sequence[str],
) -> CoreTerms | None:
    """Arma lo que se exige a las notas de un concepto abierto.

    El tema sale de lo que escribió el analista (``description``) y de las
    frases. Si lo que escribió, sin las entidades ni el lugar, no tiene
    ninguna palabra de contenido («LockBit», «Eternal en Jalisco»), no se
    exige tema: las frases de la IA agregan palabras («ataque», «filtra»)
    que el analista no pidió y tirarían «Detienen al líder de LockBit».

    Args:
        description: Lo que escribió el analista.
        keywords: Frases del concepto (en la búsqueda rápida, el literal
            primero).
        required_terms: Términos obligatorios (ADR-0113).
        place_names: Cómo se nombra la región en la consulta: sus palabras
            no son tema.

    Returns:
        Lo que se exige, o ``None`` si no hay nada que exigir.

    Example:
        >>> core_terms_for("hacker eternal", ["hacker eternal"], ["eternal"], [])
        CoreTerms(required=('eternal',), roots=('HACK',))
    """
    excluded = (*required_terms, *place_names)
    own = theme_roots([description], excluded)
    roots = theme_roots([description, *keywords], excluded) if own or not required_terms else ()
    if not required_terms and not roots:
        return None
    return CoreTerms(tuple(required_terms), roots)


def term_aliases(term: str) -> tuple[str, ...]:
    """Las formas, normalizadas, con que una nota nombra un término obligatorio.

    - **Apellido.** Un nombre de dos o tres palabras sin palabras de
      enlace («Omar García Harfuch», «Luisito Comunica») cuenta también con
      su última palabra, si tiene al menos ``MIN_SURNAME_LENGTH`` letras:
      así lo nombran los títulos. Con cuatro o más ya no es seguro que sea
      un apellido («Cártel Jalisco Nueva Generación»). Con palabras de
      enlace o cortas («Fiscalía General de la República», «Los Deltas»,
      «El Mencho») es una institución o un alias, y «República» o «Deltas»
      sueltos dirían otra cosa.
    - **Sigla.** Con tres palabras de contenido o más (sin contar las de
      enlace), sus iniciales: «FGR», «CJNG», «AMLO». No si la sigla se lee
      como palabra vacía («MAS»).

    Args:
        term: Término obligatorio tal como lo escribió el analista.

    Returns:
        El término completo y, si aplican, su última palabra y su sigla.

    Example:
        >>> term_aliases("Omar García Harfuch")
        ('OMAR GARCIA HARFUCH', 'HARFUCH', 'OGH')
        >>> term_aliases("Fiscalía General de la República")
        ('FISCALIA GENERAL DE LA REPUBLICA', 'FGR')
    """
    words = _words(term)
    forms = [normalize_name(term)]
    linked = any(_is_short(w) or w in STOPWORDS or w.isdigit() for w in words)
    named = MIN_NAME_WORDS <= len(words) <= MAX_NAME_WORDS
    if named and not linked and len(words[-1]) >= MIN_SURNAME_LENGTH:
        forms.append(words[-1])
    letters = [w[0] for w in words if not (_is_short(w) or w in CONNECTORS or w.isdigit())]
    acronym = "".join(letters)
    # «Mesa Ampliada de Seguridad» daría «MAS»: cualquier nota que diga «más».
    if len(acronym) >= MIN_ACRONYM_LENGTH and acronym not in STOPWORDS:
        forms.append(acronym)
    return tuple(forms)


def _is_short(word: str) -> bool:
    """Palabra de una o dos letras («DE», «Y»): siempre de enlace."""
    return len(word) < MIN_ROOT_WORD_LENGTH


def _term_pattern(term: str) -> re.Pattern[str]:
    """El término o su apellido (``term_aliases``) como palabras completas, ya normalizado."""
    forms = "|".join(re.escape(form) for form in term_aliases(term))
    return re.compile(rf"(?<!\w)(?:{forms})(?!\w)")


def _fragment(title: str, snippet: str | None) -> str:
    """Título y fragmento en una línea, recortados a ``MAX_CONTEXT_CHARS`` en una palabra."""
    text = " ".join(f"{title}{_CONTEXT_JOIN}{snippet}".split() if snippet else title.split())
    if len(text) <= MAX_CONTEXT_CHARS:
        return text
    cut = text[: MAX_CONTEXT_CHARS - len(_ELLIPSIS)]
    space = cut.rfind(" ")
    return (cut[:space] if space > 0 else cut).rstrip(" ,;:.—") + _ELLIPSIS


@dataclass(frozen=True, slots=True)
class QueryOrigin:
    """Con qué consulta y en qué buscador llegó una nota (su procedencia).

    Es de cada nota, no de cada consulta: una misma consulta de Google web
    trae resultados orgánicos (texto completo) y carruseles (no).

    Attributes:
        provider: Proveedor (``google_news_rss``).
        label: Su nombre en pantalla («Google News RSS»).
        keywords: Frases que llevaba la consulta.
        full_text: Si ese buscador buscó la nota en su texto completo, no
            solo en el título: los de ``FULL_TEXT_PROVIDERS`` y, en Google
            web, solo los resultados orgánicos.
        section: Sección de la respuesta de Google web
            (``raw["section"]``); ``None`` en los demás proveedores.
    """

    provider: str
    label: str
    keywords: tuple[str, ...]
    full_text: bool
    section: str | None = None

    @property
    def carousel(self) -> bool:
        """Si llegó en un carrusel de Google web (videos, tweets...), no en un orgánico."""
        return self.section is not None and not self.full_text

    @property
    def full_label(self) -> str:
        """El nombre para el juez, con la sección si es un carrusel («Google web, videos»)."""
        if not self.carousel or self.section is None:
            return self.label
        return f"{self.label}, {WEB_SECTION_LABELS.get(self.section, self.section)}"

    def carries(self, term: str) -> bool:
        """Dice si este buscador encontró la nota con una consulta que llevaba ``term``.

        Args:
            term: Término obligatorio («Eternal»).

        Returns:
            ``True`` solo si busca en el texto completo y alguna frase de la
            consulta lleva el término como palabras completas.

        Example:
            >>> QueryOrigin("google_news_rss", "Google News", ("hacker eternal",), True).carries(
            ...     "Eternal")
            True
        """
        if not self.full_text:
            return False
        pattern = _term_pattern(term)
        return any(pattern.search(normalize_name(k)) for k in self.keywords)


class CoreVerdict(StrEnum):
    """Qué pasó con una nota en el filtro de palabras."""

    CONFIRMED = "confirmed"
    """Nombra las entidades y el tema: pasa."""
    UNCONFIRMED = "unconfirmed"
    """Pasa, pero una entidad no está en el título ni en el fragmento: la
    encontró un buscador de texto completo con ella («por confirmar»)."""
    NO_ENTITY = "no_entity"
    """No nombra una entidad y ningún buscador de texto completo la trajo con ella."""
    OFF_THEME = "off_theme"
    """No trae ninguna raíz del tema (solo se pide fuera de los buscadores de
    texto completo)."""

    @property
    def kept(self) -> bool:
        """Si la nota sigue hacia el juez."""
        return self in (CoreVerdict.CONFIRMED, CoreVerdict.UNCONFIRMED)


class CoreMatcher:
    """Revisa el título y el fragmento de una nota contra un ``CoreTerms``."""

    def __init__(self, core: CoreTerms) -> None:
        """Prepara los patrones.

        Args:
            core: Lo que se exige.
        """
        self._required = tuple((term, _term_pattern(term)) for term in core.required)
        self._roots = frozenset(core.roots)

    @property
    def required(self) -> tuple[str, ...]:
        """Los términos obligatorios, tal como los escribió el analista."""
        return tuple(term for term, _ in self._required)

    def missing_terms(
        self, title: str, snippet: str | None, source: str | None = None
    ) -> tuple[str, ...]:
        """Los términos obligatorios que el título y el fragmento no nombran.

        Args:
            title: Título de la nota.
            snippet: Fragmento, si hay.
            source: Canal o autor de una publicación de un carrusel
                («YouTube · La Saga»); ``None`` para no contarlo.

        Returns:
            Los que faltan, en su orden; vacío si están todos.

        Example:
            >>> CoreMatcher(CoreTerms(("Eternal",), ())).missing_terms("Hackean Buró Laboral", None)
            ('Eternal',)
        """
        extra = " ".join(part for part in (snippet, source) if part)
        text = _text_norm(title, extra or None)
        return tuple(term for term, pattern in self._required if pattern.search(text) is None)

    def entity_context(
        self, notes: Iterable[tuple[str, str | None]], terms: Sequence[str]
    ) -> tuple[str, ...]:
        """Lo que dicen de unas entidades las notas de la búsqueda que sí las nombran.

        Revisión del 18/11/2026 (hallazgo 4): con solo el título, el juez no
        distinguía «Revelan listas negras laborales; vende hacker datos»
        (el hackeo de Eternal al Buró Laboral) de «Ariana Grande demanda a
        hackers» (ruido de Google): las dos son del tema y ninguna nombra a
        Eternal. Con lo que se sabe de Eternal por otras notas, solo la
        primera coincide con un hecho concreto.

        Args:
            notes: Título y fragmento de las notas de la búsqueda, en su
                orden (las primeras son las que mejor puso el buscador).
            terms: Entidades que la nota por juzgar no nombra
                (``missing_terms``); solo cuentan las de este ``CoreTerms``.

        Returns:
            Hasta ``MAX_CONTEXT_FRAGMENTS`` fragmentos de hasta
            ``MAX_CONTEXT_CHARS`` caracteres, de notas que nombran todas esas
            entidades, sin repetir título. Vacío si no hay entidades o
            ninguna nota las nombra.

        Example:
            >>> notes = [("El hacker Eternal vende datos del Buró Laboral", None)]
            >>> CoreMatcher(CoreTerms(("Eternal",), ())).entity_context(notes, ("Eternal",))
            ('El hacker Eternal vende datos del Buró Laboral',)
        """
        patterns = [pattern for term, pattern in self._required if term in terms]
        if not patterns:
            return ()
        seen: set[str] = set()
        found: list[str] = []
        for title, snippet in notes:
            text = _text_norm(title, snippet)
            key = normalize_name(title)
            if key in seen or not all(p.search(text) for p in patterns):
                continue
            seen.add(key)
            found.append(_fragment(title, snippet))
            if len(found) == MAX_CONTEXT_FRAGMENTS:
                break
        return tuple(found)

    def on_theme(self, title: str, snippet: str | None) -> bool:
        """Dice si el título o el fragmento traen una raíz del tema.

        Args:
            title: Título de la nota.
            snippet: Fragmento, si hay.

        Returns:
            ``True`` si trae alguna, o si no hay tema que exigir.
        """
        if not self._roots:
            return True
        return any(stem(word) in self._roots for word in _WORD.findall(_text_norm(title, snippet)))

    def check(
        self, title: str, snippet: str | None, origin: QueryOrigin, source: str | None = None
    ) -> CoreVerdict:
        """Decide si la nota pasa al juez, según cómo llegó (ver el docstring del módulo).

        - Texto completo: no se mira el tema; solo la entidad, con la
          excepción por procedencia.
        - Carrusel de Google web: con entidad, basta nombrarla en el título,
          el fragmento o el canal o autor; sin entidad, se pide el tema.
        - Lo demás: tema y entidad en el título o el fragmento.

        Args:
            title: Título de la nota.
            snippet: Fragmento, si hay.
            origin: Consulta y buscador que la trajeron (su procedencia).
            source: Medio, canal o autor de la nota (``RawArticle.source_name``);
                solo cuenta en los carruseles, donde no hay fragmento.

        Returns:
            El veredicto (``kept`` dice si pasa).

        Example:
            >>> core = CoreTerms(("Eternal",), ("HACK",))
            >>> rss = QueryOrigin("google_news_rss", "Google News", ("hacker eternal",), True)
            >>> CoreMatcher(core).check("Hackean Buró Laboral", None, rss)
            <CoreVerdict.UNCONFIRMED: 'unconfirmed'>
            >>> videos = QueryOrigin(
            ...     "searchapi_web", "Google web", ("hacker eternal",), False, "inline_videos")
            >>> CoreMatcher(core).check("ETERNAL expone 746 MIL cuentas", None, videos, "La Saga")
            <CoreVerdict.CONFIRMED: 'confirmed'>
        """
        if origin.full_text:
            return self._entity_verdict(self.missing_terms(title, snippet), origin)
        if origin.carousel and self._required:
            missing = self.missing_terms(title, snippet, source)
            return CoreVerdict.NO_ENTITY if missing else CoreVerdict.CONFIRMED
        if not self.on_theme(title, snippet):
            return CoreVerdict.OFF_THEME
        return self._entity_verdict(self.missing_terms(title, snippet), origin)

    @staticmethod
    def _entity_verdict(missing: Sequence[str], origin: QueryOrigin) -> CoreVerdict:
        """Confirmada si no falta ninguna; sin confirmar si la procedencia las cubre."""
        if not missing:
            return CoreVerdict.CONFIRMED
        if all(origin.carries(term) for term in missing):
            return CoreVerdict.UNCONFIRMED
        return CoreVerdict.NO_ENTITY
