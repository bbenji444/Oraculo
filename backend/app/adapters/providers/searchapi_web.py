"""Adaptador de SearchApi, motor ``google``: la búsqueda web normal de Google (ADR-0115).

Benji (18/11/2026) buscó «Hacker Eternal» y no llegó nada de Facebook, X ni
YouTube, que en Google sí salen. Google News no indexa publicaciones de
redes; la búsqueda web sí. Usa la misma llave y la misma cuenta de créditos
que el adaptador de Google News (``searchapi.py``).

Documentación: https://www.searchapi.io/docs/google (consultada el 18/11/2026)

- ``GET /api/v1/search?engine=google&q=…``; la llave va en el encabezado
  ``Authorization: Bearer``. Cada página que responde 200 cuesta 1 crédito.
- ``gl`` (país), ``hl`` (idioma), ``time_period`` o ``time_period_min`` y
  ``time_period_max`` (los mismos valores que Google News) y ``page``.
- ``nfpr=1``: «To exclude these auto-corrected results, set the value to
  1». Benji no quiere que se cambie su texto («Hacker» no es «Hackeo»).
- No se usan ``verbatim`` (con fechas, Google ignora el filtro de tiempo),
  ``num`` (retirado: siempre 10 por página) ni ``link`` (retirado).

Confirmado con la respuesta real del 18/11/2026 (fixture
``searchapi_web_hacker_eternal_7d.json``: «hacker eternal», gl=mx, hl=es,
nfpr=1, time_period=last_week; 200):

- Trae ``organic_results`` (9), ``inline_videos`` (4) y ``pagination``.
- ``source`` dice la red («Facebook · Ignacio Gómez Villaseñor», «X ·
  ivillasenor», «YouTube · La Saga - US», «Instagram · ivillasenor87») o el
  medio («Quinta Fuerza»). ``domain`` falta en muchas: el dominio se toma
  del link ya resuelto.
- 7 de los 9 ``link`` son ``https://www.google.com/goto?url=…``: son
  redirecciones 302 a la URL real (medido con curl el 18/11/2026: una
  lleva a quintafuerza.mx, otra a youtube.com/shorts). Aquí se piden **sin
  seguirlas** y se lee ``Location``.
- Pero si se le piden varias seguidas, Google contesta 200 con su página
  «Verificando tu solicitud» en lugar de redirigir (medido el 18/11/2026:
  en una búsqueda real 8 de 10 links quedaron así y se perdían). Esa
  verificación no se intenta pasar: el resultado **se queda con su link de
  Google**, que en el navegador del analista sí abre, y ya no se le piden
  a Google los demás links de esa página. El juez lo lee con título y
  fragmento (la extracción no descarga links de Google).
- ``date`` viene a veces y en texto («hace 15 horas», «hace 5 días»):
  lo convierte ``parse_result_date``; sin fecha queda ``None``.
- Los títulos largos vienen cortados con « ...»: se quitan los puntos y la
  nota queda marcada (``title_truncated``) para reconocerla junto a la del
  título completo.
- ``favicon`` e ``image`` traen imágenes en base64 enormes: no se guardan.
- El medio se guarda tal como lo da Google («Milenio»); la sección va en
  ``raw["section"]`` (revisión del 18/11/2026: la marca «Noticias · » que
  se le ponía salía en el CSV y en los reportes).

Sin saldo o con la llave rechazada, SearchApi responde con error: el
adaptador lo deja como ``ProviderNoCreditsError`` o ``ProviderAuthError``,
sin reintentos, y ``ExecuteQueries`` sigue con las demás fuentes y avisa.
Un link de Google que no se puede resolver (verificación de Google,
redirección mal formada, error de red o de ``httpx2``) se queda como vino;
nunca tumba la búsqueda.

Secciones que se leen (las de la documentación que son publicaciones):
``organic_results``, ``inline_videos``, ``inline_shorts``, ``inline_tweets``,
``top_stories``, ``discussions_and_forums`` y ``perspectives``. Se ignoran
anuncios, shopping, mapas, ``knowledge_graph``, ``related_questions`` y
``ai_overview``: no son notas y el resumen de Google no se reproduce
(CLAUDE.md §8).

No hace: no descarga las páginas de las notas (eso es la extracción) ni pide
más de ``SEARCHAPI_WEB_MAX_PAGES`` páginas por consulta.
"""

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from urllib.parse import parse_qs, parse_qsl, urljoin, urlsplit, urlunsplit

import httpx2

from app.adapters.providers.http import ProviderHttpClient
from app.adapters.providers.searchapi import (
    CREDITS_PER_PAGE,
    FALLBACK_COUNTRY,
    LANGUAGE,
    SEARCHAPI_URL,
    time_params,
)
from app.application.clock import MEXICO_CITY
from app.application.ports.providers import ProviderResponse
from app.domain.articles import InvalidArticleError, RawArticle
from app.domain.errors import (
    ProviderError,
    ProviderNoCreditsError,
    ProviderNotConfiguredError,
    ProviderResponseError,
)
from app.domain.platforms import LABEL_SEPARATOR, is_google_redirect
from app.domain.queries import PlannedQuery, Provider
from app.domain.result_dates import parse_result_date

logger = logging.getLogger(__name__)

ENGINE = "google"
# nfpr=1: Google no autocorrige la consulta (documentación del motor google).
NO_AUTOCORRECT = "1"
# Una página = 10 resultados = 1 crédito. Por defecto solo la primera: a la
# cuenta le quedaban 47 créditos de prueba que no se renuevan (18/11/2026).
DEFAULT_MAX_PAGES = 1
# Resolver un link google.com/goto es leer un 302 de Google: tarda
# milisegundos. 5 s bastan y una redirección lenta no frena la búsqueda.
GOTO_TIMEOUT_SECONDS = 5.0
# Un intento: si Google no responde, la nota se descarta (no vale la espera).
GOTO_MAX_ATTEMPTS = 1
# Hasta 10 links por página; 4 a la vez para no parecer un ataque a Google.
GOTO_MAX_CONCURRENCY = 4
# Respuestas de SearchApi que significan «sin créditos». La documentación
# (https://www.searchapi.io/docs/account-api, 18/11/2026) solo dice que con 0
# búsquedas restantes «searches are rejected», sin el código: 402 (Payment
# Required) y 429 (también el de pasar el límite por hora, que con 200000 por
# hora no nos toca) son lo común en estos servicios. No se reintentan.
# VERIFICAR: el código y el texto reales cuando la cuenta llegue a 0.
# La llave rechazada (401/403) ya es ``ProviderAuthError`` y tampoco se reintenta.
NO_CREDIT_STATUSES = frozenset({402, 429})
# Secciones de la respuesta, en el orden en que se toman (la primera vez que
# sale un link es la que cuenta).
SECTIONS = (
    "organic_results",
    "inline_videos",
    "inline_shorts",
    "inline_tweets",
    "top_stories",
    "discussions_and_forums",
    "perspectives",
)
# Campos con imágenes en base64 (decenas de KB cada uno): no van a ``raw``.
_HEAVY_FIELDS = frozenset({"favicon", "thumbnail", "image", "images"})
# Marcas de título cortado que pone Google («... de ...», «… de …»).
_TRUNCATION_MARKS = ("...", "…")
_GOOGLE_DOMAIN = "google.com"
# google.com/goto?url=<token> es una redirección que hay que pedir;
# google.com/url?q=<destino> ya trae el destino en el propio link.
_GOTO_PATH = "/goto"
_URL_PATH = "/url"
_URL_TARGET_PARAMS = ("q", "url")
_REDIRECTS = range(300, 400)
_WEB_SCHEMES = frozenset({"http", "https"})
_X_LABEL = "X"
# Entre el código y el cuerpo en los mensajes de ``ProviderHttpClient``.
_HTTP_DETAIL_SEPARATOR = "): "


@dataclass(frozen=True, slots=True)
class WebHit:
    """Un resultado de Google web antes de resolver su link.

    Attributes:
        section: Sección de la respuesta (``organic_results``...).
        link: Link tal como vino (puede ser ``google.com/goto``).
        title: Título, con los puntos suspensivos si Google lo cortó.
        source_name: Medio o red con su autor («X · ivillasenor»).
        date_text: Fecha en texto («hace 15 horas»), si vino.
        snippet: Fragmento, si vino.
        raw: El resultado sin imágenes, con su sección.
    """

    section: str
    link: str
    title: str | None
    source_name: str | None
    date_text: str | None
    snippet: str | None
    raw: dict[str, object]


@dataclass(frozen=True, slots=True)
class WebPage:
    """Lo que trajo una página de la búsqueda web.

    Attributes:
        hits: Resultados con link, en orden de sección y posición.
        discarded: Resultados sin link.
        has_next: Si Google ofrece otra página (``pagination.next``).
    """

    hits: tuple[WebHit, ...]
    discarded: int
    has_next: bool


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _joined(*parts: object) -> str | None:
    """«YouTube · La Saga»: las partes que vinieron, con el separador de Google."""
    texts = [t for t in (_text(p) for p in parts) if t]
    return LABEL_SEPARATOR.join(texts) or None


def untruncated(title: str | None) -> tuple[str | None, bool]:
    """Quita los puntos suspensivos con que Google corta un título largo.

    Args:
        title: Título tal como vino.

    Returns:
        El título sin « ...» al final y si estaba cortado.

    Example:
        >>> untruncated("Hackean 746 mil cuentas de celular, incluidas las de ...")
        ('Hackean 746 mil cuentas de celular, incluidas las de', True)
    """
    clean = (title or "").strip()
    for mark in _TRUNCATION_MARKS:
        if clean.endswith(mark):
            return clean[: -len(mark)].rstrip(" ,;:") or None, True
    return clean or None, False


def _raw(item: Mapping[str, object], section: str) -> dict[str, object]:
    return {**{k: v for k, v in item.items() if k not in _HEAVY_FIELDS}, "section": section}


def _hit(section: str, item: Mapping[str, object]) -> WebHit | None:
    """Un resultado de cualquier sección en el formato común, o ``None`` sin link."""
    link = _text(item.get("link"))
    if link is None:
        return None
    source = item.get("source")
    title: object = item.get("title")
    snippet: object = item.get("snippet")
    name: str | None
    if section == "inline_videos":
        name = _joined(source, item.get("channel"))
    elif section in ("inline_shorts", "perspectives"):
        name = _joined(source, item.get("author"))
        title = title or snippet
    elif section == "discussions_and_forums":
        name = _joined(source, item.get("community"))
    else:
        name = _text(source)
    return WebHit(
        section=section,
        link=link,
        title=_text(title),
        source_name=name,
        date_text=_text(item.get("date")),
        snippet=_text(snippet),
        raw=_raw(item, section),
    )


def _tweet_hit(tweet: Mapping[str, object]) -> WebHit | None:
    """Un tweet de ``inline_tweets``: título con su autor y el texto como fragmento."""
    link = _text(tweet.get("link"))
    if link is None:
        return None
    author = tweet.get("author")
    who = author if isinstance(author, dict) else {}
    name, screen = _text(who.get("name")), _text(who.get("screen_name"))
    handle = f"@{screen}" if screen else None
    who_text = f"{name} ({handle})" if name and handle else name or handle or "Publicación"
    title = f"{who_text} en X"
    return WebHit(
        section="inline_tweets",
        link=link,
        title=title,
        source_name=_joined(_X_LABEL, screen),
        date_text=_text(tweet.get("date")),
        snippet=_text(tweet.get("snippet")),
        raw=_raw(tweet, "inline_tweets"),
    )


def _tweets(value: object) -> list[Mapping[str, object]]:
    """Los tweets de ``inline_tweets``. # VERIFICAR: la documentación los pone en ``tweets[]``."""
    if isinstance(value, dict):
        value = value.get("tweets", [])
    if not isinstance(value, list):
        return []
    found: list[Mapping[str, object]] = []
    for entry in value:
        if isinstance(entry, dict) and isinstance(entry.get("tweets"), list):
            found.extend(t for t in entry["tweets"] if isinstance(t, dict))
        elif isinstance(entry, dict):
            found.append(entry)
    return found


# Lo que contesta SearchApi, con HTTP 200, cuando Google no encontró nada
# (su especificación, openapi/google.yaml: «Error message when the page has
# no results»). Búsqueda real del 18/11/2026, «Pillofon Luisito Comunica» en
# la última semana: el HTML guardado por SearchApi dice «No se han
# encontrado resultados para tu búsqueda». No es una falla: es una página
# vacía, y sí cobra su crédito (medido con el saldo). Tomarlo como error
# dejaba la búsqueda «parcial», como si hubiera algo que reintentar
# (sección 3 del ADR-0115).
NO_RESULTS_ERROR = "Google didn't return any results."


def parse_page(body: str) -> WebPage:
    """Lee una página de la respuesta de SearchApi (motor ``google``).

    Args:
        body: Cuerpo JSON de la respuesta.

    Returns:
        Los resultados con link de las secciones que son publicaciones.

    Raises:
        ProviderResponseError: Si el cuerpo no es JSON o trae un error que
            no sea «sin resultados» (``NO_RESULTS_ERROR``: página vacía).
    """
    provider = Provider.SEARCHAPI_WEB.value
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(
            f"Google web (SearchApi) no respondió JSON: {body[:200]}", provider=provider
        ) from exc
    if not isinstance(data, dict):
        raise ProviderResponseError("Google web respondió un JSON inesperado.", provider=provider)
    error = data.get("error")
    if isinstance(error, str) and error.strip() == NO_RESULTS_ERROR:
        return WebPage((), 0, has_next=False)
    if isinstance(error, str):
        raise ProviderResponseError(f"Google web (SearchApi): {error}", provider=provider)
    hits: list[WebHit] = []
    discarded = 0
    for section in SECTIONS:
        value = data.get(section)
        if value is None:
            continue
        if section == "inline_tweets":
            candidates = [_tweet_hit(t) for t in _tweets(value)]
        elif isinstance(value, list):
            candidates = [_hit(section, i) if isinstance(i, dict) else None for i in value]
        else:
            candidates = []
        hits.extend(h for h in candidates if h is not None)
        discarded += sum(1 for h in candidates if h is None)
    pagination = data.get("pagination")
    has_next = isinstance(pagination, dict) and bool(_text(pagination.get("next")))
    return WebPage(tuple(hits), discarded, has_next)


def _is_google(host: str) -> bool:
    return host == _GOOGLE_DOMAIN or host.endswith(f".{_GOOGLE_DOMAIN}")


def _usable(url: str | None) -> str | None:
    """El link si lleva a un sitio real (http(s) y no de Google); si no, ``None``."""
    if not url:
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in _WEB_SCHEMES or not host or _is_google(host):
        return None
    return url


def _direct(url: str) -> str | None:
    """Resuelve sin red un link: el de un sitio o el destino de ``google.com/url?q=``.

    Args:
        url: Link de un resultado o ``Location`` de una redirección.

    Returns:
        El link usable, o ``None`` si no lleva a un sitio real (otra página de
        Google, incluida otra redirección ``goto``, que ya no se sigue).

    Raises:
        ValueError: Si el link está mal formado (``resolve`` lo atrapa).
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not _is_google(host):
        return _usable(url)
    if parts.path == _URL_PATH:
        query = parse_qs(parts.query)
        return next((_usable(query[k][0]) for k in _URL_TARGET_PARAMS if k in query), None)
    return None


class SearchApiWebProvider:
    """``NewsProviderPort`` para la búsqueda web de Google por SearchApi."""

    def __init__(
        self,
        http: ProviderHttpClient | None,
        resolver: ProviderHttpClient | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Recibe los dos clientes HTTP.

        Args:
            http: Cliente de SearchApi con la llave en sus encabezados, o
                ``None`` si no hay llave.
            resolver: Cliente **sin llave** y sin seguir redirecciones, para
                leer a dónde llevan los links ``google.com/goto``. Sin él,
                esos resultados se descartan.
            max_pages: Páginas máximas por consulta (``SEARCHAPI_WEB_MAX_PAGES``).
            now: Reloj para las fechas relativas («hace 5 días»).
        """
        self._http = http
        self._resolver = resolver
        self._max_pages = max(1, max_pages)
        self._now = now

    @property
    def provider(self) -> Provider:
        """Ver ``NewsProviderPort.provider``."""
        return Provider.SEARCHAPI_WEB

    def is_configured(self) -> bool:
        """Solo funciona con ``SEARCHAPI_API_KEY`` en ``.env``."""
        return self._http is not None

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        """Ver ``NewsProviderPort.request_params`` (la llave no va aquí).

        En «Mundo» (ADR-0112) va ``gl=mx``, a diferencia de Google News: en
        la búsqueda web ``gl`` es el país de quien busca y solo acomoda los
        resultados, no los filtra. Sin él, SearchApi busca como desde Estados
        Unidos y «Hacker Eternal» trajo 2 resultados, contra 9 páginas y 4
        videos con gl=mx, lo que ve Benji en Google (medido el 18/11/2026).
        """
        country = FALLBACK_COUNTRY if query.country.worldwide else query.country.iso_a2
        return {
            "engine": ENGINE,
            "q": query.text,
            "gl": (country or FALLBACK_COUNTRY).lower(),
            "hl": LANGUAGE,
            "nfpr": NO_AUTOCORRECT,
            **time_params(query.window),
        }

    def estimate_cost(self, query: PlannedQuery) -> int:
        """Lo más que puede costar: todas las páginas permitidas."""
        return CREDITS_PER_PAGE * self._max_pages

    async def resolve(self, link: str, *, ask_google: bool = True) -> str | None:
        """A dónde lleva un link de un resultado.

        Nunca lanza (revisión del 18/11/2026, hallazgo 6: un ``Location`` mal
        formado o un error de ``httpx2`` tumbaba la consulta entera).

        Args:
            link: Link tal como vino de Google.
            ask_google: Si se le pregunta a Google a dónde lleva un
                ``google.com/goto``. ``_articles`` lo apaga en cuanto Google
                contesta con su verificación, para no insistir.

        Returns:
            El mismo link si ya es de un sitio; el destino si es una
            redirección de Google que se pudo leer (también cuando el
            ``Location`` es otro ``google.com/url?q=``); el mismo
            ``google.com/goto`` si Google no redirigió (en el navegador del
            analista sí abre); ``None`` si el link está mal formado o es otra
            página de Google (la nota se descarta).
        """
        try:
            parts = urlsplit(link)
            if not (_is_google((parts.hostname or "").lower()) and parts.path == _GOTO_PATH):
                return _direct(link)
        except ValueError:
            return None
        target = await self._follow(link) if ask_google else None
        return target or link

    async def _follow(self, link: str) -> str | None:
        """Le pregunta a Google a dónde lleva un ``google.com/goto``, sin seguirlo.

        Args:
            link: El ``google.com/goto`` (ya revisado que está bien formado).

        Returns:
            El destino, o ``None`` si Google no redirigió a un sitio (su
            página de verificación, otra página de Google, un error o un
            ``Location`` mal formado) o no hay con qué preguntar.
        """
        if self._resolver is None:
            return None
        try:
            parts = urlsplit(link)
            # La consulta del link va como parámetros: httpx2 reemplaza la de la
            # URL por los que recibe, y sin ``url=<token>`` Google no redirige
            # (lo atrapó la prueba con la respuesta real).
            response = await self._resolver.get(
                urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")),
                dict(parse_qsl(parts.query, keep_blank_values=True)),
            )
            location = response.headers.get("location")
            if response.status_code not in _REDIRECTS or not location:
                return None
            return _direct(urljoin(link, location))
        except (ProviderError, httpx2.HTTPError, httpx2.InvalidURL, ValueError) as error:
            # ``ProviderHttpClient`` traduce la red y los códigos HTTP, pero un
            # ``Location`` raro puede romper ``urlsplit``/``httpx2`` (ValueError,
            # InvalidURL) o la descompresión (DecodingError, un HTTPError).
            logger.info(f"Google web: link sin destino ({type(error).__name__})")
            return None

    async def _targets(self, page: WebPage) -> list[str | None]:
        """El link con que se queda cada resultado de la página, en orden.

        Uno por uno: si Google contesta un ``goto`` sin redirigir (su página
        «Verificando tu solicitud»), los demás ``goto`` de la página ya no se
        le piden y se quedan como vinieron. No se intenta pasar la
        verificación.
        """
        targets: list[str | None] = []
        ask_google = True
        for hit in page.hits:
            target = await self.resolve(hit.link, ask_google=ask_google)
            if ask_google and target is not None and is_google_redirect(target):
                ask_google = False
            targets.append(target)
        return targets

    async def _articles(self, page: WebPage) -> tuple[list[RawArticle], int]:
        """Resuelve los links de una página y arma sus notas (la posición se fija después)."""
        targets = await self._targets(page)
        articles: list[RawArticle] = []
        discarded = 0
        now = self._now()
        for hit, url in zip(page.hits, targets, strict=True):
            if url is None:
                discarded += 1
                continue
            title, truncated = untruncated(hit.title)
            try:
                articles.append(
                    RawArticle.create(
                        provider=Provider.SEARCHAPI_WEB,
                        provider_rank=len(articles) + 1,
                        url=url,
                        title=title,
                        source_name=hit.source_name,
                        published_at=parse_result_date(hit.date_text, now, MEXICO_CITY),
                        snippet=hit.snippet,
                        raw=hit.raw,
                        title_truncated=truncated,
                    )
                )
            except InvalidArticleError:
                discarded += 1
        kept = sum(1 for t in targets if t is not None and is_google_redirect(t))
        if kept:
            logger.info(f"Google web: {kept} links de Google sin redirigir; se quedan así")
        return articles, discarded

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        """Ver ``NewsProviderPort.search``.

        Raises:
            ProviderNotConfiguredError: Si falta la llave.
            ProviderNoCreditsError: Si SearchApi dice que no hay saldo
                (``NO_CREDIT_STATUSES``); ``ExecuteQueries`` sigue con las
                demás fuentes y avisa.
            ProviderAuthError: Si SearchApi rechaza la llave (401/403).
            ProviderError: Si la primera página falla por otra razón.
        """
        if self._http is None:
            raise ProviderNotConfiguredError(
                "Falta SEARCHAPI_API_KEY en .env.", provider=Provider.SEARCHAPI_WEB.value
            )
        params = self.request_params(query)
        articles: list[RawArticle] = []
        seen: set[str] = set()
        discarded = 0
        bodies: list[str] = []
        charged = 0
        status = 0
        for number in range(1, self._max_pages + 1):
            page_params = params if number == 1 else {**params, "page": str(number)}
            try:
                response = await self._http.get(SEARCHAPI_URL, page_params)
            except ProviderError as error:
                if number == 1:
                    raise _explained(error) from error
                # Una página extra que falla no tira las anteriores, y un error
                # HTTP no se cobra (solo las respuestas 200).
                break
            charged += CREDITS_PER_PAGE
            try:
                page = parse_page(response.text)
            except ProviderResponseError:
                if number == 1:
                    raise
                break
            status = response.status_code
            bodies.append(response.text)
            found, dropped = await self._articles(page)
            discarded += page.discarded + dropped
            for article in found:
                if article.url in seen:
                    discarded += 1
                    continue
                seen.add(article.url)
                articles.append(replace(article, provider_rank=len(articles) + 1))
            if not page.has_next:
                break
        pages = len(bodies)
        return ProviderResponse(
            articles=tuple(articles),
            http_status=status,
            params={**params, "pages": str(pages)},
            body=bodies[0] if pages == 1 else json.dumps([json.loads(b) for b in bodies]),
            discarded=discarded,
            credits_used=charged,
            pages=pages,
        )


def _explained(error: ProviderError) -> ProviderError:
    """El error de la primera página, como error de saldo si SearchApi dijo «sin créditos».

    ``ExecuteQueries`` reconoce ``ProviderNoCreditsError`` y
    ``ProviderAuthError`` (llave rechazada, 401/403, que se deja igual) y
    sigue con las demás fuentes con un aviso, sin marcar la búsqueda como
    parcial (ADR-0115).

    Args:
        error: Lo que respondió SearchApi.

    Returns:
        ``ProviderNoCreditsError`` con el texto de SearchApi si el código es
        de saldo (``NO_CREDIT_STATUSES``); si no, el mismo error.
    """
    if (
        not isinstance(error, ProviderNoCreditsError)
        and error.http_status not in NO_CREDIT_STATUSES
    ):
        return error
    # ``ProviderHttpClient`` escribe «<proveedor> ... (HTTP n): <cuerpo>»: se
    # conserva solo el cuerpo, que es lo que dijo SearchApi.
    detail = error.message.split(_HTTP_DETAIL_SEPARATOR, 1)[-1]
    return ProviderNoCreditsError(
        f"SearchApi no tiene créditos (HTTP {error.http_status}): {detail}",
        provider=Provider.SEARCHAPI_WEB.value,
        http_status=error.http_status,
    )
