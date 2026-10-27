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
encontraron, con su posición. Si el grupo trae el link de Google News y el
del medio, se conserva el del medio (F12.1b): es el que el analista puede
abrir y el que identifica al medio.

``match_known`` aplica la misma regla contra notas ya guardadas (nivel 2 de
duplicados, ADR-0025): la misma nota que llega en otra búsqueda con otro
link se reutiliza en lugar de guardarse otra vez.

No hace: no consulta la base (los candidatos los trae el pipeline).
"""

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.domain.articles import RawArticle
from app.domain.names import normalize_name

# Similitud mínima de títulos para "casi iguales" (§9).
NEAR_DUPLICATE_SIMILARITY = 0.9
# Ventana de fechas para "casi iguales" (§9): el mismo hecho publicado un día
# después por otro medio sigue siendo la misma nota.
NEAR_DUPLICATE_WINDOW = timedelta(days=1)
# Google News vuelve a dar notas viejas con otra liga y una fecha días después.
# Medido el 27/10/2026: «Don Rodo, hermano de El Mencho, gana amparo a la FGR»
# (oem.com.mx) llegó con fecha del 23/10 y otra vez del 26/10, y se guardó dos
# veces. El mismo medio con el mismo título exacto es la misma nota dentro de
# esta ventana.
SAME_OUTLET_WINDOW = timedelta(days=7)
# Pero un medio sí repite títulos cortos: sus columnas («Portafolios Político»,
# «Se pudrió el PAN») salen con el mismo nombre en días distintos.
SAME_OUTLET_MIN_WORDS = 6
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
# Host de los links de Google News RSS: no llevan directo al medio (ADR-0021).
GOOGLE_NEWS_HOST = "news.google.com"
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
        article: La nota que se conserva (la primera que llegó, o la que trae
            el link del medio si la primera era de Google News).
        url_canonical: Su URL canónica.
        title_norm: Su título normalizado.
        sightings: Todos los proveedores que la encontraron.
        known_id: Id de la misma nota ya guardada con otro link, si la hay
            (lo pone el pipeline con ``match_known``).
    """

    article: RawArticle
    url_canonical: str
    title_norm: str
    sightings: list[Sighting] = field(default_factory=list)
    known_id: int | None = None


def _close(
    title_a: str,
    published_a: datetime | None,
    title_b: str,
    published_b: datetime | None,
    similarity: TitleSimilarity,
) -> bool:
    """Regla de «casi iguales» (§9): título ≥ 0.9 de parecido y fechas a ±1 día."""
    if published_a is None or published_b is None:
        # Sin fechas no se puede comprobar la ventana: solo cuenta el título idéntico.
        return title_a == title_b
    if abs(published_a - published_b) > NEAR_DUPLICATE_WINDOW:
        return False
    return similarity(title_a, title_b) >= NEAR_DUPLICATE_SIMILARITY


def _near(a: DedupedArticle, b: RawArticle, title_b: str, similarity: TitleSimilarity) -> bool:
    return _close(a.title_norm, a.article.published_at, title_b, b.published_at, similarity)


def is_google_news(url: str) -> bool:
    """Dice si el link es de Google News (no lleva directo al medio).

    Args:
        url: URL de la nota.

    Returns:
        ``True`` si el host es ``news.google.com``.

    Example:
        >>> is_google_news("https://news.google.com/rss/articles/CBMi...")
        True
    """
    return (urlsplit(url).hostname or "").lower() == GOOGLE_NEWS_HOST


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
        elif is_google_news(match.url_canonical) and not is_google_news(url):
            # Misma nota: nos quedamos con el link del medio, no con el de Google.
            match.article, match.url_canonical, match.title_norm = article, url, title
        by_url[url] = match
        if sighting not in match.sightings:
            match.sightings.append(sighting)
    return kept


@dataclass(frozen=True, slots=True)
class KnownArticle:
    """Una nota ya guardada, candidata a ser la misma que una nueva.

    Attributes:
        article_id: Id en ``articles``.
        url_canonical: Su URL canónica.
        title_norm: Su título normalizado.
        published_at: Su fecha (UTC), si la tiene.
        source_domain: Dominio de su medio, si se conoce.
    """

    article_id: int
    url_canonical: str
    title_norm: str
    published_at: datetime | None
    source_domain: str | None = None


def _same_outlet(known: KnownArticle, item: DedupedArticle) -> bool:
    """Mismo medio, mismo título exacto (largo) y a ≤ ``SAME_OUTLET_WINDOW``."""
    domain = item.article.source_domain
    published = item.article.published_at
    return (
        domain is not None
        and known.source_domain == domain
        and known.title_norm == item.title_norm
        and len(item.title_norm.split()) >= SAME_OUTLET_MIN_WORDS
        and known.published_at is not None
        and published is not None
        and abs(known.published_at - published) <= SAME_OUTLET_WINDOW
    )


def match_known(
    item: DedupedArticle, known: Sequence[KnownArticle], similarity: TitleSimilarity
) -> KnownArticle | None:
    """Busca, entre notas ya guardadas, la misma nota que ``item`` con otro link.

    Usa la misma regla que ``dedupe`` (título ≥ 0.9 de parecido y ±1 día),
    o el mismo medio con el mismo título exacto a ≤ 7 días: Google News
    vuelve a dar notas viejas con otra fecha. Si varias cumplen, gana la de
    título más parecido.

    Args:
        item: Nota nueva, ya sin duplicados dentro de su búsqueda.
        known: Candidatas que trajo la base (pueden no cumplir la regla).
        similarity: Similitud de dos títulos normalizados, de 0 a 1.

    Returns:
        La nota guardada que es la misma, o ``None``.

    Example:
        >>> match_known(nota_de_google_news, [misma_nota_del_medio], rapidfuzz).article_id
        1504
    """
    published = item.article.published_at
    matches = [
        k
        for k in known
        if k.url_canonical != item.url_canonical
        and (
            _close(k.title_norm, k.published_at, item.title_norm, published, similarity)
            or _same_outlet(k, item)
        )
    ]
    return max(matches, key=lambda k: similarity(k.title_norm, item.title_norm), default=None)
