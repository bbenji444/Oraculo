"""Nota del índice local (ADR-0013): lo que la ingesta guarda y en qué se busca.

Una ``NewsItem`` es la versión mínima de una nota: metadatos y link, nunca el
texto completo (CLAUDE.md §8). La ingesta la arma desde un archivo GKG de
GDELT o desde un RSS de un medio; el proveedor ``indice_local`` busca sobre
``text_norm`` (título + fragmento normalizados, conservando la Ñ).

Reglas de qué se guarda de GDELT:

- **GKG** (ADR-0013): notas **en español** con **alguna ubicación en México**.
  Las ubicaciones de GDELT se guardan solo como pistas (``gdelt_states``): en
  la muestra real tenían errores, y la ubicación final la decide F4 con INEGI.
- **Ngramas** (ADR-0014): notas **en español** que **mencionan México** en el
  título o el cuerpo (``MexicoMentions``). De ellas se guardan además las
  frases del cuerpo (``body_terms``), solo para buscar: nunca se muestran.

No hace: no lee formatos de archivo ni consulta la base.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from app.domain.articles import domain_of
from app.domain.names import normalize_name
from app.domain.text_repair import clean_text

# Código de idioma de GDELT para el español (campo TranslationInfo, srclc:spa).
SPANISH = "spa"
# Código de país de México en las ubicaciones de GDELT (FIPS 10-4).
MEXICO_FIPS = "MX"
GDELT_SOURCE = "gdelt_gkg"
GDELT_NGRAMS_SOURCE = "gdelt_ngrams"
RSS_SOURCE_PREFIX = "rss:"
_WEB_SCHEMES = frozenset({"http", "https"})
# Separa las frases del cuerpo en body_terms: así una búsqueda de dos palabras
# no "pega" el final de una frase con el inicio de otra.
BODY_SEPARATOR = " | "
# Tope de frases por nota. En la muestra real del 16/10/2026 el promedio fue
# 437; el tope evita que una nota enorme infle la base.
MAX_BODY_PHRASES = 2000
# Palabras que nombran al país; se suman a los estados del catálogo.
MEXICO_WORDS = ("México", "mexicano", "mexicana", "mexicanos", "mexicanas")
_MEXICAN_TLD = ".mx"
# Nivel 2 de duplicados en el índice (ADR-0025): el mismo medio con el mismo
# texto en esta ventana es la misma nota con otro link (variantes ``%20``,
# títulos de portada como «INICIO | PERIODICO CIUDADCCS» ×151). Medido el
# 24/10/2026: 2,899 notas sobrantes así. Tres días cubre las republicaciones
# sin juntar columnas que repiten título cada semana.
SAME_OUTLET_WINDOW = timedelta(days=3)
# Un título necesita letras: «🎦» solo (73 notas al 24/10/2026) no es una nota.
MIN_TITLE_LETTERS = 2


def index_text_norm(title: str, snippet: str | None) -> str:
    """Texto en el que busca ``indice_local``: título y fragmento normalizados.

    Es la única fórmula de ``news_index.text_norm``: la usan la ingesta y la
    reparación de Mojibake (``make reparar-texto``) para que coincidan.

    Args:
        title: Título de la nota.
        snippet: Fragmento, si hay.

    Returns:
        El texto normalizado (mayúsculas, sin acentos, con Ñ).
    """
    return normalize_name(f"{title} {snippet or ''}")


class InvalidNewsError(ValueError):
    """Una nota no se puede guardar (sin URL web, sin título o sin fecha)."""


@dataclass(frozen=True, slots=True)
class GdeltLocation:
    """Una ubicación tal como la reporta GDELT (pista, no ubicación final).

    Attributes:
        kind: Tipo de GDELT (1 país, 2 estado, 3 y 4 ciudad).
        name: Nombre completo ("Saltillo, Coahuila De Zaragoza, Mexico").
        country: Código FIPS del país ("MX").
        adm1: Código FIPS del estado ("MX07"), vacío si es el país.
        lat: Latitud, si viene.
        lon: Longitud, si viene.
    """

    kind: int
    name: str
    country: str
    adm1: str
    lat: float | None
    lon: float | None


@dataclass(frozen=True, slots=True)
class NewsItem:
    """Una nota lista para el índice local.

    Attributes:
        source: ``gdelt_gkg`` o ``rss:<medio>``.
        url: Link a la nota.
        title: Título limpio.
        snippet: Fragmento, si la fuente lo trae.
        source_name: Nombre del medio.
        source_domain: Dominio del medio.
        published_at: Fecha (UTC).
        language: Idioma que reporta la fuente.
        gdelt_states: Claves INEGI de los estados donde GDELT la ubicó.
        gdelt_locations: Ubicaciones de GDELT (pistas).
        gdelt_themes: Temas de GDELT.
        body_terms: Frases del cuerpo normalizadas y separadas por
            ``BODY_SEPARATOR``, solo para buscar (ngramas, ADR-0014).
    """

    source: str
    url: str
    title: str
    snippet: str | None
    source_name: str | None
    source_domain: str | None
    published_at: datetime
    language: str | None
    gdelt_states: tuple[str, ...] = ()
    gdelt_locations: tuple[GdeltLocation, ...] = ()
    gdelt_themes: tuple[str, ...] = ()
    body_terms: str | None = None

    @property
    def text_norm(self) -> str:
        """Título y fragmento normalizados: sobre esto busca ``indice_local``."""
        return index_text_norm(self.title, self.snippet)

    @classmethod
    def create(  # noqa: PLR0913 — un argumento por campo de la nota, todos por nombre (*)
        cls,
        *,
        source: str,
        url: str,
        title: str | None,
        published_at: datetime | None,
        snippet: str | None = None,
        source_name: str | None = None,
        source_domain: str | None = None,
        language: str | None = None,
        gdelt_states: Sequence[str] = (),
        gdelt_locations: Sequence[GdeltLocation] = (),
        gdelt_themes: Sequence[str] = (),
        body_phrases: Iterable[str] = (),
    ) -> "NewsItem":
        """Valida y limpia una nota.

        Args:
            source: Origen.
            url: Link absoluto ``http(s)``.
            title: Título; no puede quedar vacío.
            published_at: Fecha con zona; sin fecha no se puede buscar por rango.
            snippet: Fragmento.
            source_name: Medio.
            source_domain: Dominio; si falta, se toma de la URL.
            language: Idioma.
            gdelt_states: Claves INEGI de estado.
            gdelt_locations: Ubicaciones de GDELT (las repetidas se guardan una vez).
            gdelt_themes: Temas de GDELT.
            body_phrases: Frases del cuerpo (ngramas); se normalizan, se
                quitan repetidas y se guardan hasta ``MAX_BODY_PHRASES``.

        Returns:
            La nota.

        Raises:
            InvalidNewsError: Si falta URL web, fecha con zona o un título con al
                menos ``MIN_TITLE_LETTERS`` letras.
        """
        clean_url = url.strip()
        parts = urlsplit(clean_url)
        if parts.scheme not in _WEB_SCHEMES or not parts.netloc:
            raise InvalidNewsError(f"URL no válida: {url!r}")
        # clean_text también repara el Mojibake: GDELT trae títulos de algunos
        # medios (tiempo.com.mx, puentelibre.mx) ya rotos (F12.1).
        clean_title = clean_text(title)
        if not clean_title or sum(c.isalpha() for c in clean_title) < MIN_TITLE_LETTERS:
            raise InvalidNewsError(f"Nota sin título: {url!r}")
        if published_at is None or published_at.tzinfo is None:
            raise InvalidNewsError(f"Nota sin fecha con zona: {url!r}")
        return cls(
            source=source,
            url=clean_url,
            title=clean_title,
            snippet=clean_text(snippet),
            source_name=clean_text(source_name),
            source_domain=(source_domain or domain_of(clean_url) or "").lower() or None,
            published_at=published_at.astimezone(UTC),
            language=language,
            gdelt_states=tuple(dict.fromkeys(gdelt_states)),
            # GDELT repite la ubicación por cada mención; basta una vez como pista.
            gdelt_locations=tuple(dict.fromkeys(gdelt_locations)),
            gdelt_themes=tuple(dict.fromkeys(gdelt_themes)),
            body_terms=body_terms_from(body_phrases),
        )


def keep_gdelt_note(language: str | None, locations: Sequence[GdeltLocation]) -> bool:
    """Dice si una nota del GKG entra al índice: en español y con México.

    Args:
        language: Idioma original según GDELT (``spa``).
        locations: Ubicaciones que encontró GDELT.

    Returns:
        ``True`` si está en español y alguna ubicación es de México.
    """
    return language == SPANISH and any(loc.country == MEXICO_FIPS for loc in locations)


def inegi_states(
    locations: Sequence[GdeltLocation], fips_to_inegi: dict[str, str]
) -> tuple[str, ...]:
    """Claves INEGI de los estados de México donde GDELT ubicó una nota.

    Args:
        locations: Ubicaciones de GDELT.
        fips_to_inegi: Tabla ``geodata/fips_inegi.csv`` (``MX07`` → ``05``).

    Returns:
        Claves INEGI sin repetir, en el orden en que aparecen. Las
        ubicaciones a nivel país (sin estado) no aportan clave.
    """
    states = [
        fips_to_inegi[loc.adm1]
        for loc in locations
        if loc.country == MEXICO_FIPS and loc.adm1 in fips_to_inegi
    ]
    return tuple(dict.fromkeys(states))


def body_terms_from(phrases: Iterable[str]) -> str | None:
    """Arma ``body_terms``: frases normalizadas, sin repetir, en su orden.

    Args:
        phrases: Frases del cuerpo tal como las da la fuente.

    Returns:
        Las frases unidas con ``BODY_SEPARATOR`` (hasta ``MAX_BODY_PHRASES``),
        o ``None`` si no hay ninguna.

    Example:
        >>> body_terms_from(["Robo en  Peñón", "robo en peñón", "de los Baños"])
        'ROBO EN PEÑON | DE LOS BAÑOS'
    """
    unique: dict[str, None] = {}
    for phrase in phrases:
        clean = normalize_name(phrase)
        if clean:
            unique[clean] = None
            if len(unique) == MAX_BODY_PHRASES:
                break
    return BODY_SEPARATOR.join(unique) or None


class MexicoMentions:
    """Reconoce si una nota menciona México: el país, un estado o un dominio ``.mx``.

    Es el filtro de los ngramas (ADR-0014): GDELT no da ubicaciones en ese
    conjunto, así que se mira el texto. Los nombres se comparan completos y
    normalizados ("NUEVO LEON" no coincide dentro de otra palabra). Deja pasar
    algunas notas de otros países (por ejemplo, un apellido "Guerrero"): son
    candidatas, y F4 decide su ubicación con el catálogo INEGI.
    """

    def __init__(self, state_terms: Iterable[str]) -> None:
        """Arma el reconocedor.

        Args:
            state_terms: Nombres y términos curados de los 32 estados (del
                catálogo ``regions``); se suman las palabras del país.
        """
        clean = {normalize_name(term) for term in (*MEXICO_WORDS, *state_terms)}
        # Los más largos primero: "BAJA CALIFORNIA SUR" antes que "BAJA CALIFORNIA".
        ordered = sorted((term for term in clean if term), key=len, reverse=True)
        alternatives = "|".join(re.escape(term) for term in ordered)
        self._pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")

    def found_in(self, text_norm: str, domain: str | None = None) -> bool:
        """Dice si el texto (o el dominio del medio) apunta a México.

        Args:
            text_norm: Título y frases ya normalizados.
            domain: Dominio del medio, si se conoce.

        Returns:
            ``True`` si el dominio termina en ``.mx`` o el texto nombra al
            país o a un estado.
        """
        if domain is not None and domain.endswith(_MEXICAN_TLD):
            return True
        return self._pattern.search(text_norm) is not None
