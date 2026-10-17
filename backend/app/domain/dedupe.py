"""Quitar notas duplicadas de una búsqueda (especificación §9, paso 3).

La misma nota llega varias veces: de Google News (SearchApi), de los ngramas
de GDELT y del RSS del medio, a veces con la URL decorada (``utm_*``,
``fbclid``) o en su versión AMP. Aquí se decide cuáles son la misma:

- **Iguales:** misma URL canónica (``canonical_url``).
- **Casi iguales:** títulos normalizados con similitud ≥ 0.9 y fechas a
  ±1 día. La similitud la calcula una función que se recibe como parámetro
  (en producción, rapidfuzz desde un adaptador): el dominio no importa
  librerías externas (CLAUDE.md §6.1).

Se conserva una nota por grupo y se anotan **todos** los proveedores que la
encontraron, con su posición.

No hace: no consulta la base (reutilizar notas de búsquedas anteriores es
del pipeline).
"""

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.domain.articles import RawArticle
from app.domain.names import normalize_name

# Similitud mínima de títulos para "casi iguales" (§9).
NEAR_DUPLICATE_SIMILARITY = 0.9
# Ventana de fechas para "casi iguales" (§9): el mismo hecho publicado un día
# después por otro medio sigue siendo la misma nota.
NEAR_DUPLICATE_WINDOW = timedelta(days=1)
# Parámetros que solo rastrean de dónde vino el clic; no cambian la nota.
_TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ocid",
        "cmpid",
        "smid",
        "_ga",
        "ref",
        "ref_src",
        # Versión AMP de los medios con Arc (El Universal, Infobae).
        "outputtype",
    }
)
_TRACKING_PREFIXES = ("utm_",)
_WWW = "www."
_AMP_SUFFIXES = ("/amp", "/amp/")

TitleSimilarity = Callable[[str, str], float]


def canonical_url(url: str) -> str:
    """URL con la que se compara una nota: sin rastreo, sin ``www.`` ni AMP.

    Args:
        url: URL tal como llegó del proveedor.

    Returns:
        URL en ``https``, dominio en minúsculas sin ``www.``, sin fragmento,
        sin parámetros de rastreo (los demás, ordenados) y sin ``/amp`` final
        ni diagonal final.

    Example:
        >>> canonical_url("http://www.Milenio.com/nota/?utm_source=x&id=2#top")
        'https://milenio.com/nota?id=2'
    """
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith(_WWW):
        host = host[len(_WWW) :]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = parts.path or "/"
    for suffix in _AMP_SUFFIXES:
        if path.endswith(suffix) and len(path) > len(suffix):
            path = path[: -len(suffix)]
    if len(path) > 1:
        path = path.rstrip("/")
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith(_TRACKING_PREFIXES)
    )
    return urlunsplit(("https", host, path, urlencode(query), ""))


def url_hash(canonical: str) -> str:
    """Huella corta de la URL canónica (llave única de ``articles``).

    Args:
        canonical: URL de ``canonical_url``.

    Returns:
        SHA-256 en hexadecimal.
    """
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Sighting:
    """Un proveedor que encontró la nota y en qué posición.

    Attributes:
        provider: Proveedor (``searchapi``, ``indice_local``...).
        rank: Posición en sus resultados.
    """

    provider: str
    rank: int


@dataclass(slots=True)
class DedupedArticle:
    """Una nota después de quitar duplicados.

    Attributes:
        article: La nota que se conserva (la primera que llegó).
        url_canonical: Su URL canónica.
        title_norm: Su título normalizado.
        sightings: Todos los proveedores que la encontraron.
    """

    article: RawArticle
    url_canonical: str
    title_norm: str
    sightings: list[Sighting] = field(default_factory=list)


def _near(a: DedupedArticle, b: RawArticle, title_b: str, similarity: TitleSimilarity) -> bool:
    if a.article.published_at is None or b.published_at is None:
        # Sin fechas no se puede comprobar la ventana: solo cuenta el título idéntico.
        return a.title_norm == title_b
    if abs(a.article.published_at - b.published_at) > NEAR_DUPLICATE_WINDOW:
        return False
    return similarity(a.title_norm, title_b) >= NEAR_DUPLICATE_SIMILARITY


def dedupe(articles: Sequence[RawArticle], similarity: TitleSimilarity) -> list[DedupedArticle]:
    """Agrupa las notas iguales o casi iguales, en el orden en que llegaron.

    Args:
        articles: Notas de todos los proveedores de una búsqueda.
        similarity: Similitud de dos títulos normalizados, de 0 a 1.

    Returns:
        Una entrada por nota distinta, con todos sus proveedores.

    Example:
        >>> [len(d.sightings) for d in dedupe([nota_google, misma_nota_gdelt], rapidfuzz)]
        [2]
    """
    kept: list[DedupedArticle] = []
    by_url: dict[str, DedupedArticle] = {}
    for article in articles:
        url = canonical_url(article.url)
        title = normalize_name(article.title)
        sighting = Sighting(article.provider.value, article.provider_rank)
        match = by_url.get(url) or next(
            (k for k in kept if _near(k, article, title, similarity)), None
        )
        if match is None:
            match = DedupedArticle(article, url, title)
            kept.append(match)
            by_url[url] = match
        if sighting not in match.sightings:
            match.sightings.append(sighting)
    return kept
