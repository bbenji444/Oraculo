"""Dónde se publicó una nota: en un medio, en una red social o en otro sitio (ADR-0115).

Benji (18/11/2026) quiere ver los resultados «como Google», fraccionados por
plataforma, y poder quedarse solo con Facebook o solo con X. La plataforma
se calcula **al leer**, con lo que ya se guarda de cada nota (dominio del
medio, link y proveedores que la encontraron), así que vale también para las
notas viejas y no necesita columna nueva.

La regla, en orden:

1. **Red social por dominio:** el del medio (``source_domain``) y, si no, el
   del link. Cuenta el dominio exacto o un subdominio suyo: ``m.facebook.com``
   es Facebook, pero ``box.com`` no es X. Los links de Google
   (``news.google.com``) no dicen nada: Google News RSS da Facebook con
   ``source_domain = facebook.com`` y el link de Google.
2. **Red social por el nombre que da Google**, solo si no hay un dominio útil:
   Google web escribe «Facebook · Autor», «X · usuario», «YouTube · canal».
3. **Si no es red social:** «Noticias» si la encontró un proveedor de prensa
   (SearchApi Google News, Google News RSS, GDELT, índice local); si solo la
   trajo Google web, «Otros sitios». Una noticia destacada de Google web
   (``top_stories``) casi siempre la trae también el RSS con el mismo texto
   y entonces es «Noticias». Desde la revisión del 18/11/2026 el medio se
   guarda limpio («Milenio», sin la marca «Noticias · »): la marca salía en
   el CSV y en los reportes. La sección no se guarda en la base (sin
   migración), así que la destacada que solo trajo Google web queda en
   «Otros sitios».

Los valores de ``Platform`` son un contrato con el frontend (``platform`` de
cada nota en la API): no se cambian sin cambiar los dos lados.

No hace: no consulta la base ni descarga nada.
"""

from collections.abc import Iterable
from enum import StrEnum
from urllib.parse import urlsplit

from app.domain.articles import domain_of
from app.domain.queries import Provider


class Platform(StrEnum):
    """Plataforma de una nota; los valores son el contrato con el frontend."""

    NEWS = "news"
    FACEBOOK = "facebook"
    X = "x"
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    WEB = "web"


# Nombres en pantalla (los mismos del frontend), para el CSV y los reportes.
PLATFORM_LABELS: dict[Platform, str] = {
    Platform.NEWS: "Noticias",
    Platform.FACEBOOK: "Facebook",
    Platform.X: "X",
    Platform.YOUTUBE: "YouTube",
    Platform.INSTAGRAM: "Instagram",
    Platform.TIKTOK: "TikTok",
    Platform.REDDIT: "Reddit",
    Platform.TELEGRAM: "Telegram",
    Platform.WEB: "Otros sitios",
}
# Dominios de cada red (los oficiales y sus links cortos: fb.watch, youtu.be,
# instagr.am, redd.it, t.me). Se comparan exactos o como sufijo «.dominio».
_SOCIAL_DOMAINS: dict[str, Platform] = {
    "facebook.com": Platform.FACEBOOK,
    "fb.com": Platform.FACEBOOK,
    "fb.watch": Platform.FACEBOOK,
    "x.com": Platform.X,
    "twitter.com": Platform.X,
    "youtube.com": Platform.YOUTUBE,
    "youtu.be": Platform.YOUTUBE,
    "instagram.com": Platform.INSTAGRAM,
    "instagr.am": Platform.INSTAGRAM,
    "tiktok.com": Platform.TIKTOK,
    "reddit.com": Platform.REDDIT,
    "redd.it": Platform.REDDIT,
    "t.me": Platform.TELEGRAM,
    "telegram.org": Platform.TELEGRAM,
}
# Primera parte del «source» de Google web antes de « · » (medido en la
# respuesta real del 18/11/2026: «Facebook · Ignacio Gómez Villaseñor»,
# «X · ivillasenor», «YouTube · La Saga - US», «Instagram · ivillasenor87»).
_LABEL_PLATFORMS: dict[str, Platform] = {
    "facebook": Platform.FACEBOOK,
    "x": Platform.X,
    "twitter": Platform.X,
    "youtube": Platform.YOUTUBE,
    "instagram": Platform.INSTAGRAM,
    "tiktok": Platform.TIKTOK,
    "reddit": Platform.REDDIT,
    "telegram": Platform.TELEGRAM,
}
SOCIAL_PLATFORMS = frozenset(_LABEL_PLATFORMS.values())
# Proveedores que solo buscan en prensa: lo que traen es una noticia.
NEWS_PROVIDERS = frozenset(
    {
        Provider.SEARCHAPI.value,
        Provider.GOOGLE_NEWS_RSS.value,
        Provider.GDELT.value,
        Provider.LOCAL_INDEX.value,
    }
)
# Separador que usa Google entre la plataforma y el autor («X · usuario»).
LABEL_SEPARATOR = " · "
# Hosts de Google: sus links son redirecciones y no dicen dónde se publicó.
_GOOGLE_DOMAIN = "google.com"
# Ruta de las redirecciones de Google web (``https://www.google.com/goto?url=…``).
_GOTO_PATH = "/goto"


def _matches(host: str, domain: str) -> bool:
    """Dominio exacto o subdominio suyo (``m.facebook.com`` sí; ``box.com`` no es ``x.com``)."""
    return host == domain or host.endswith(f".{domain}")


def _is_google(host: str) -> bool:
    return _matches(host, _GOOGLE_DOMAIN)


def is_google_redirect(url: str) -> bool:
    """Dice si el link es una redirección ``google.com/goto`` de Google web.

    Google web (ADR-0115) da así muchos resultados. Si Google no la resolvió
    (contestó con su página «Verificando tu solicitud»), la nota se queda
    con ese link: abre en el navegador del analista, pero no se descarga.

    Args:
        url: Link de la nota.

    Returns:
        ``True`` si es de Google y su ruta es ``/goto``; ``False`` si no o si
        el link está mal formado.

    Example:
        >>> is_google_redirect("https://www.google.com/goto?url=CAES")
        True
        >>> is_google_redirect("https://quintafuerza.mx/nota")
        False
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    return _is_google((parts.hostname or "").lower()) and parts.path == _GOTO_PATH


def social_platform(domain: str | None) -> Platform | None:
    """La red social de un dominio, si es de una.

    Args:
        domain: Dominio («m.facebook.com», «x.com»), con o sin ``www.``.

    Returns:
        La red, o ``None`` si no es una red social.

    Example:
        >>> social_platform("m.facebook.com")
        <Platform.FACEBOOK: 'facebook'>
        >>> social_platform("box.com") is None
        True
    """
    host = (domain or "").strip().lower().rstrip(".")
    if not host:
        return None
    return next((p for d, p in _SOCIAL_DOMAINS.items() if _matches(host, d)), None)


def _label_platform(label: str | None) -> Platform | None:
    """La red que nombra el «source» de Google («Facebook · Autor» → Facebook)."""
    if not label:
        return None
    head = label.split(LABEL_SEPARATOR.strip(), 1)[0].strip().lower()
    return _LABEL_PLATFORMS.get(head)


def platform_of(
    source_domain: str | None,
    url: str,
    providers: Iterable[str],
    source_label: str | None = None,
) -> Platform:
    """Dónde se publicó una nota.

    Args:
        source_domain: Dominio del medio que se guardó (``articles.source_domain``).
        url: Link de la nota.
        providers: Proveedores que la encontraron (``searchapi``,
            ``searchapi_web``...).
        source_label: Nombre del medio (``articles.source_name``); en Google
            web dice la red («X · usuario»).

    Returns:
        La plataforma. Sin proveedores (notas de antes) cuenta como noticia.

    Example:
        >>> platform_of("facebook.com", "https://news.google.com/rss/x", ["google_news_rss"])
        <Platform.FACEBOOK: 'facebook'>
        >>> platform_of("quintafuerza.mx", "https://quintafuerza.mx/n", ["searchapi_web"])
        <Platform.WEB: 'web'>
    """
    domains = [d for d in (source_domain, domain_of(url)) if d and not _is_google(d.lower())]
    for domain in domains:
        found = social_platform(domain)
        if found is not None:
            return found
    if not domains:
        by_label = _label_platform(source_label)
        if by_label is not None:
            return by_label
    found_by = set(providers)
    if not found_by or found_by & NEWS_PROVIDERS:
        return Platform.NEWS
    return Platform.WEB


def is_social(source_domain: str | None, url: str, source_label: str | None = None) -> bool:
    """Dice si la nota es una publicación de red social.

    Las redes no se descargan (muros de inicio de sesión) y se comparan solo
    por link: sus títulos se repiten entre publicaciones (ADR-0115).

    Args:
        source_domain: Dominio del medio.
        url: Link de la nota.
        source_label: Nombre del medio que dio el proveedor.

    Returns:
        ``True`` si es Facebook, X, YouTube, Instagram, TikTok, Reddit o Telegram.
    """
    return platform_of(source_domain, url, (), source_label) in SOCIAL_PLATFORMS
