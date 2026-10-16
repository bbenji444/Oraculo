"""Adaptador de Google News RSS (especificación §8): respaldo gratuito.

No es un servicio oficial ni documentado: puede cambiar o bloquear sin
aviso, y por eso es el proveedor de respaldo. El texto de la consulta ya trae
``when:7d`` o ``after:``/``before:`` (dialecto de
``app.domain.query_dialects``); aquí se agregan el idioma y el país
(``hl``, ``gl``, ``ceid``).

Decisión del plan aprobado de F3: **no se resuelven los links**. Apuntan a
``news.google.com`` con un identificador codificado; el truco de
decodificarlos dejó de funcionar en 2024 y seguir la redirección hace que
Google limite las peticiones. Se guarda el link de Google, el medio sale de
``<source url="…">`` y F4 deduplica estas notas por título y fecha.

El XML se lee con ``defusedxml`` para no exponerse a XML malicioso.

No hace: no deduplica ni lee las notas.
"""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import ParseError, fromstring

from app.adapters.providers.http import ProviderHttpClient
from app.application.clock import MEXICO_CITY
from app.application.ports.providers import ProviderResponse
from app.domain.articles import InvalidArticleError, RawArticle, domain_of
from app.domain.errors import ProviderResponseError
from app.domain.queries import CountryFilter, DateWindow, PlannedQuery, Provider

RSS_URL = "https://news.google.com/rss/search"
# Español latinoamericano: la edición de Google News que cubre a México.
LANGUAGE = "es-419"
# Si un país no tiene código ISO-2 (territorios en disputa), se usa la
# edición de México: el sistema está enfocado en México.
FALLBACK_COUNTRY = "MX"
_TITLE_SEPARATOR = " - "


def edition_params(country: CountryFilter) -> dict[str, str]:
    """Idioma y país de la edición de Google News.

    Args:
        country: País de la consulta.

    Returns:
        ``hl``, ``gl`` y ``ceid``, por ejemplo ``ceid=MX:es-419``.
    """
    code = country.iso_a2 or FALLBACK_COUNTRY
    return {"hl": LANGUAGE, "gl": code, "ceid": f"{code}:{LANGUAGE}"}


def strip_source_suffix(title: str, source: str | None) -> str:
    """Quita el " - Medio" que Google agrega al final del título.

    Args:
        title: Título del RSS ("Ataque a alcaldía - Milenio").
        source: Nombre del medio ("Milenio").

    Returns:
        El título sin el sufijo, si coincide con el medio.
    """
    suffix = f"{_TITLE_SEPARATOR}{source}" if source else None
    if suffix and title.endswith(suffix):
        return title[: -len(suffix)]
    return title


def _text(item: Element, tag: str) -> str | None:
    found = item.find(tag)
    return found.text if found is not None and found.text else None


def _published(item: Element) -> datetime | None:
    value = _text(item, "pubDate")
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    # RFC 2822: "-0000" significa "en UTC, zona de origen desconocida", y
    # Python lo devuelve sin zona. Google publica en GMT.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_items(body: str, window: DateWindow | None = None) -> tuple[list[RawArticle], int]:
    """Convierte el XML del RSS en notas del formato común.

    Args:
        body: XML de la respuesta.
        window: Si se da, se descartan las notas fechadas fuera del rango:
            Google ignora ``after:``/``before:`` (medido el 16/10/2026).

    Returns:
        Las notas válidas y cuántos ``<item>`` se descartaron (inválidos o
        fuera del rango).

    Raises:
        ProviderResponseError: Si no es un RSS legible.
    """
    try:
        root: Element = fromstring(body)
    except ParseError as exc:
        raise ProviderResponseError(
            f"Google News RSS no respondió un XML válido: {body[:200]}",
            provider=Provider.GOOGLE_NEWS_RSS.value,
        ) from exc
    articles: list[RawArticle] = []
    discarded = 0
    for rank, item in enumerate(root.iter("item"), start=1):
        source = item.find("source")
        source_name = source.text if source is not None else None
        source_url = source.get("url") if source is not None else None
        title = _text(item, "title")
        published = _published(item)
        if (
            window is not None
            and published is not None
            and not window.contains(published, MEXICO_CITY)
        ):
            discarded += 1
            continue
        try:
            articles.append(
                RawArticle.create(
                    provider=Provider.GOOGLE_NEWS_RSS,
                    provider_rank=rank,
                    url=_text(item, "link") or "",
                    title=strip_source_suffix(title, source_name) if title else None,
                    source_name=source_name,
                    source_domain=domain_of(source_url) if source_url else None,
                    published_at=published,
                    raw={"guid": _text(item, "guid"), "pubDate": _text(item, "pubDate")},
                )
            )
        except InvalidArticleError:
            discarded += 1
    return articles, discarded


class GoogleNewsRssProvider:
    """``NewsProviderPort`` para Google News RSS."""

    def __init__(self, http: ProviderHttpClient) -> None:
        """Recibe el cliente HTTP ya configurado.

        Args:
            http: Cliente HTTP de Google News.
        """
        self._http = http

    @property
    def provider(self) -> Provider:
        """Ver ``NewsProviderPort.provider``."""
        return Provider.GOOGLE_NEWS_RSS

    def is_configured(self) -> bool:
        """El RSS no necesita llave."""
        return True

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        """Ver ``NewsProviderPort.request_params``."""
        return {"q": query.text, **edition_params(query.country)}

    def estimate_cost(self, query: PlannedQuery) -> int:
        """El RSS es gratuito."""
        return 0

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        """Ver ``NewsProviderPort.search``."""
        params = self.request_params(query)
        response = await self._http.get(RSS_URL, params)
        articles, discarded = parse_items(response.text, query.window)
        return ProviderResponse(
            articles=tuple(articles),
            http_status=response.status_code,
            params=params,
            body=response.text,
            discarded=discarded,
        )
