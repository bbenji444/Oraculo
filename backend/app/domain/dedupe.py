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

Google web (ADR-0115) agrega tres reglas:

- **Redes sociales, solo por link.** Las publicaciones de una misma página
  repiten título («Ignacio Gómez Villaseñor on X»): por título se juntarían
  publicaciones distintas. Los alias de cada red (``m.facebook.com``,
  ``twitter.com``, ``youtu.be``) se vuelven uno en ``canonical_url``. La
  única excepción es la misma publicación que llega por Google News RSS (con
  el link de Google) y por Google web (con el link real): misma red, mismo
  texto largo y fechas cercanas (``_same_post``); se queda el link real.
- **Títulos cortados.** Google web corta los títulos largos («Hackean 746
  mil cuentas de ...»). Un título cortado es la misma nota que la de título
  completo si coincide palabra por palabra al inicio; la que se conserva
  se queda con el título completo.
- **Mejor link.** Si la nota guardada tenía el link de Google News y llega el
  del medio (``refreshes_link``), el pipeline vuelve a leer su texto.

No hace: no consulta la base (los candidatos los trae el pipeline).
"""

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.domain.articles import RawArticle
from app.domain.names import normalize_name
from app.domain.platforms import is_social

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
# Un título cortado por Google web cuenta como la misma nota si sus primeras
# palabras son las del título completo. Se piden al menos 6, como en
# SAME_OUTLET_MIN_WORDS: con menos, inicios genéricos («Detienen a dos...»)
# juntarían notas distintas.
TRUNCATED_MIN_WORDS = 6
# Las fechas relativas de Google web («hace 5 días») tienen un día de
# redondeo: a la ventana de casi iguales (±1 día) se le suma ese día.
TRUNCATED_TITLE_WINDOW = NEAR_DUPLICATE_WINDOW + timedelta(days=1)
# La misma publicación de una red por el RSS y por Google web (revisión del
# 18/11/2026): se pide un texto de al menos 6 palabras, como en
# SAME_OUTLET_MIN_WORDS. Con menos suele ser el nombre de la página («Ignacio
# Gómez Villaseñor»), que se repite en todas sus publicaciones.
SAME_POST_MIN_WORDS = SAME_OUTLET_MIN_WORDS
# Hosts de la misma red con otro nombre (ADR-0115): la versión móvil o la
# marca anterior. La misma publicación llega con cualquiera de ellos.
_HOST_ALIASES = {
    "m.facebook.com": "facebook.com",
    "mobile.facebook.com": "facebook.com",
    "twitter.com": "x.com",
    "mobile.twitter.com": "x.com",
    "m.twitter.com": "x.com",
    "mobile.x.com": "x.com",
    "m.youtube.com": "youtube.com",
}
# Link corto de YouTube: youtu.be/<id> es youtube.com/watch?v=<id>.
_YOUTU_BE = "youtu.be"
_YOUTUBE = "youtube.com"
_YOUTUBE_WATCH = "/watch"
_YOUTUBE_VIDEO_PARAM = "v"
# Parámetros de YouTube que solo dicen cómo se compartió el link (si=, feature=).
_YOUTUBE_TRACKING = frozenset({"si", "feature"})
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
        ni diagonal final. Las redes quedan con un solo host (ADR-0115):
        ``m.facebook.com`` → ``facebook.com``, ``twitter.com`` → ``x.com`` y
        ``youtu.be/<id>`` → ``youtube.com/watch?v=<id>``.

    Example:
        >>> canonical_url("http://www.Milenio.com/nota/?utm_source=x&id=2#top")
        'https://milenio.com/nota?id=2'
        >>> canonical_url("https://youtu.be/jMs7fCiEHRo?si=abc")
        'https://youtube.com/watch?v=jMs7fCiEHRo'
    """
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith(_WWW):
        host = host[len(_WWW) :]
    host = _HOST_ALIASES.get(host, host)
    params = parse_qsl(parts.query, keep_blank_values=True)
    path = parts.path or "/"
    if host == _YOUTU_BE and len(path) > 1:
        host = _YOUTUBE
        params = [(_YOUTUBE_VIDEO_PARAM, path.strip("/")), *params]
        path = _YOUTUBE_WATCH
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    for suffix in _AMP_SUFFIXES:
        if path.endswith(suffix) and len(path) > len(suffix):
            path = path[: -len(suffix)]
    if len(path) > 1:
        path = path.rstrip("/")
    extra_tracking = _YOUTUBE_TRACKING if host == _YOUTUBE else frozenset()
    query = sorted(
        (key, value)
        for key, value in params
        if key.lower() not in _TRACKING_PARAMS
        and key.lower() not in extra_tracking
        and not key.lower().startswith(_TRACKING_PREFIXES)
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
        refresh_text: Si la nota guardada tenía el link de Google News y ahora
            llegó el del medio (``refreshes_link``): su texto se vuelve a leer
            si antes solo se tuvo título y fragmento (ADR-0115).
    """

    article: RawArticle
    url_canonical: str
    title_norm: str
    sightings: list[Sighting] = field(default_factory=list)
    known_id: int | None = None
    refresh_text: bool = False


def _prefix_of(short: str, full: str) -> bool:
    """El título cortado ``short`` es el inicio de ``full`` (su última palabra puede ir partida)."""
    cut, whole = short.split(), full.split()
    if len(cut) < TRUNCATED_MIN_WORDS or len(cut) > len(whole):
        return False
    last = len(cut) - 1
    return whole[:last] == cut[:last] and whole[last].startswith(cut[last])


def _truncated_match(
    title_a: str, published_a: datetime | None, title_b: str, published_b: datetime | None
) -> bool:
    """Un título cortado y el completo: mismo inicio y, si hay fechas, a ±2 días."""
    shorter, longer = sorted((title_a, title_b), key=len)
    if not _prefix_of(shorter, longer):
        return False
    if published_a is None or published_b is None:
        return True
    return abs(published_a - published_b) <= TRUNCATED_TITLE_WINDOW


def _close(  # noqa: PLR0913 — dos títulos con su fecha, la similitud y la marca de título cortado (*)
    title_a: str,
    published_a: datetime | None,
    title_b: str,
    published_b: datetime | None,
    similarity: TitleSimilarity,
    *,
    truncated: bool = False,
) -> bool:
    """Regla de «casi iguales» (§9): título ≥ 0.9 de parecido y fechas a ±1 día.

    Con ``truncated`` (uno de los títulos vino cortado, ADR-0115) también
    cuenta que uno sea el inicio del otro.
    """
    if truncated and _truncated_match(title_a, published_a, title_b, published_b):
        return True
    if published_a is None or published_b is None:
        # Sin fechas no se puede comprobar la ventana: solo cuenta el título idéntico.
        return title_a == title_b
    if abs(published_a - published_b) > NEAR_DUPLICATE_WINDOW:
        return False
    return similarity(title_a, title_b) >= NEAR_DUPLICATE_SIMILARITY


def _near(a: DedupedArticle, b: RawArticle, title_b: str, similarity: TitleSimilarity) -> bool:
    truncated = a.article.title_truncated or b.title_truncated
    return _close(
        a.title_norm,
        a.article.published_at,
        title_b,
        b.published_at,
        similarity,
        truncated=truncated,
    )


def _social(article: RawArticle) -> bool:
    return is_social(article.source_domain, article.url, article.source_name)


def _network_host(domain: str | None) -> str | None:
    """Dominio de una red sin ``www.`` ni su alias (``m.facebook.com`` → ``facebook.com``)."""
    host = (domain or "").strip().lower()
    if host.startswith(_WWW):
        host = host[len(_WWW) :]
    return _HOST_ALIASES.get(host, host) or None


def _same_text(
    title_a: str,
    published_a: datetime | None,
    title_b: str,
    published_b: datetime | None,
    *,
    truncated: bool,
) -> bool:
    """Mismo texto largo (o uno cortado que es el inicio del otro) y, con fechas, a ±2 días."""
    if (
        published_a is not None
        and published_b is not None
        and abs(published_a - published_b) > TRUNCATED_TITLE_WINDOW
    ):
        return False
    if title_a == title_b:
        return len(title_a.split()) >= SAME_POST_MIN_WORDS
    return truncated and _truncated_match(title_a, published_a, title_b, published_b)


def _same_post(kept: DedupedArticle, article: RawArticle, url: str, title: str) -> bool:
    """La misma publicación de una red por Google News RSS y por Google web.

    Revisión del 18/11/2026 (hallazgo 7): el RSS da la publicación con el link
    de Google News y el dominio de la red; Google web, con el link real. Solo
    por link nunca se juntaban y salía dos veces. Se juntan si una de las dos
    trae el link de Google News y la otra no, son de la misma red y dicen lo
    mismo (``_same_text``). Dos con link real nunca se juntan por texto: una
    página repite publicaciones parecidas.
    """
    if not _social(kept.article) or is_google_news(kept.url_canonical) == is_google_news(url):
        return False
    host = _network_host(article.source_domain)
    if host is None or host != _network_host(kept.article.source_domain):
        return False
    return _same_text(
        kept.title_norm,
        kept.article.published_at,
        title,
        article.published_at,
        truncated=kept.article.title_truncated or article.title_truncated,
    )


def _completed(base: RawArticle, other: RawArticle) -> RawArticle:
    """``base`` con lo que le falta tomado de ``other``, la otra copia de la misma nota.

    Si ``base`` no tenía fecha, toma la de ``other`` siempre (revisión del
    18/11/2026, hallazgo 2): Google web casi nunca trae fecha y, como va antes
    que el RSS y el índice, su nota se guardaba sin fecha aunque las otras
    copias sí la traían. Si el título de ``base`` vino cortado y el de
    ``other`` no, se queda con el completo. El link es siempre el de ``base``.
    """
    full_title = base.title_truncated and not other.title_truncated
    title = other.title if full_title else base.title
    truncated = False if full_title else base.title_truncated
    published = base.published_at or other.published_at
    if (title, truncated, published) == (base.title, base.title_truncated, base.published_at):
        return base
    return replace(base, title=title, title_truncated=truncated, published_at=published)


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
        match = by_url.get(url)
        if match is None and not _social(article):
            # Las redes solo se juntan por link (ADR-0115): las publicaciones
            # de una página repiten título y por título se volverían una.
            match = next(
                (
                    k
                    for k in kept
                    if not _social(k.article) and _near(k, article, title, similarity)
                ),
                None,
            )
        elif match is None:
            # Salvo la misma publicación por el RSS (link de Google News) y por
            # Google web (link real): se juntan y gana el link real.
            match = next((k for k in kept if _same_post(k, article, url, title)), None)
        if match is None:
            match = DedupedArticle(article, url, title)
            kept.append(match)
        elif is_google_news(match.url_canonical) and not is_google_news(url):
            # Misma nota: nos quedamos con el link del medio, no con el de
            # Google (y con el título completo si el del medio vino cortado).
            match.article = _completed(article, match.article)
            match.url_canonical = url
            match.title_norm = normalize_name(match.article.title)
        else:
            completed = _completed(match.article, article)
            if completed is not match.article:
                match.article, match.title_norm = completed, normalize_name(completed.title)
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

    Las redes sociales no se buscan por título (ADR-0115): una publicación ya
    guardada se reconoce solo por su link, y eso lo resuelve el guardado. La
    excepción es la guardada con el link de Google News (del RSS) que ahora
    llega con el link real: misma red y mismo texto largo (``_same_post``).
    Un título cortado por Google web cuenta si es el inicio del guardado.

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
    if _social(item.article):
        return _known_post(item, known)
    published = item.article.published_at
    truncated = item.article.title_truncated
    matches = [
        k
        for k in known
        if k.url_canonical != item.url_canonical
        and not is_social(k.source_domain, k.url_canonical)
        and (
            _close(
                k.title_norm,
                k.published_at,
                item.title_norm,
                published,
                similarity,
                truncated=truncated,
            )
            or _same_outlet(k, item)
        )
    ]
    return max(matches, key=lambda k: similarity(k.title_norm, item.title_norm), default=None)


def _known_post(item: DedupedArticle, known: Sequence[KnownArticle]) -> KnownArticle | None:
    """La misma publicación ya guardada con el link de Google News (ver ``_same_post``)."""
    host = _network_host(item.article.source_domain)
    if host is None or is_google_news(item.url_canonical):
        return None
    return next(
        (
            k
            for k in known
            if is_google_news(k.url_canonical)
            and _network_host(k.source_domain) == host
            and _same_text(
                k.title_norm,
                k.published_at,
                item.title_norm,
                item.article.published_at,
                truncated=item.article.title_truncated,
            )
        ),
        None,
    )


def refreshes_link(item: DedupedArticle, known: KnownArticle) -> bool:
    """Dice si la nota nueva trae el link del medio de una guardada con el de Google News.

    Pasa con Google web (ADR-0115): Google News RSS da links de Google que no
    se pueden leer y la IA solo vio el título; Google web da el link real. El
    guardado cambia el link y el pipeline vuelve a leer el texto.

    Args:
        item: Nota nueva.
        known: La misma nota ya guardada (``match_known``).

    Returns:
        ``True`` si la guardada tiene link de Google News y la nueva no.
    """
    return is_google_news(known.url_canonical) and not is_google_news(item.url_canonical)
