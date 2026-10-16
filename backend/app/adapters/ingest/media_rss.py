"""Lectura de los RSS propios de medios mexicanos (ADR-0013).

La lista curada vive en ``fuentes/medios_rss.csv``. Cada medio queda
inactivo hasta que Benji revisa sus términos de uso.

De cada nota se guardan **solo** título, fragmento corto (máximo 300
caracteres, sin HTML), fecha y link (CLAUDE.md §8). Algunos feeds (El
Universal, Infobae) traen el texto completo en ``content:encoded``: se
ignora.

El XML se lee con ``defusedxml`` para no exponerse a XML malicioso.

No hace: no guarda nada (eso es el caso de uso de ingesta).
"""

import csv
import html
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import ParseError, fromstring

from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.ingest import IngestSourceError, MediaFeed, ParseResult
from app.domain.news_index import InvalidNewsError, NewsItem
from app.geodata.fuentes import REPO_ROOT

MEDIA_FEEDS_PATH = REPO_ROOT / "fuentes" / "medios_rss.csv"
# Fragmento máximo que se guarda: suficiente para buscar, lejos del texto completo.
SNIPPET_MAX_CHARS = 300
_ACTIVE = "si"
_TAGS = re.compile(r"<[^>]+>")


class FeedError(IngestSourceError):
    """El feed no respondió un RSS legible."""


def read_feeds(path: Path = MEDIA_FEEDS_PATH) -> list[MediaFeed]:
    """Lee la lista curada de medios.

    Args:
        path: CSV con ``slug, medio, url, activo, terminos, nota``.

    Returns:
        Todos los medios, activos o no.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            MediaFeed(
                slug=row["slug"].strip(),
                name=row["medio"].strip(),
                url=row["url"].strip(),
                active=row["activo"].strip().lower() == _ACTIVE,
            )
            for row in csv.DictReader(handle)
        ]


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
    # RFC 2822: "-0000" es UTC con origen desconocido y llega sin zona.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def clean_snippet(value: str | None) -> str | None:
    """Fragmento sin HTML, sin entidades y de máximo 300 caracteres.

    Args:
        value: ``<description>`` del feed.

    Returns:
        El fragmento limpio, o ``None`` si queda vacío.
    """
    if not value:
        return None
    text = " ".join(html.unescape(_TAGS.sub(" ", value)).split())
    return text[:SNIPPET_MAX_CHARS] or None


def parse_feed(body: str | bytes, feed: MediaFeed) -> ParseResult:
    """Convierte un RSS en notas del índice.

    Args:
        body: XML del feed.
        feed: Medio al que pertenece.

    Returns:
        Las notas y los conteos.

    Raises:
        FeedError: Si no es un RSS legible.
    """
    try:
        root: Element = fromstring(body)
    except ParseError as exc:
        raise FeedError(f"{feed.name} no respondió un RSS válido.") from exc
    items: list[NewsItem] = []
    discarded = 0
    entries = list(root.iter("item"))
    for entry in entries:
        try:
            items.append(
                NewsItem.create(
                    source=feed.source,
                    url=_text(entry, "link") or "",
                    title=html.unescape(_text(entry, "title") or ""),
                    published_at=_published(entry),
                    snippet=clean_snippet(_text(entry, "description")),
                    source_name=feed.name,
                    language="es",
                )
            )
        except InvalidNewsError:
            discarded += 1
    return ParseResult(tuple(items), len(entries), discarded)


class MediaRssSource:
    """Baja y lee el RSS de un medio."""

    def __init__(self, http: ProviderHttpClient) -> None:
        """Recibe el cliente HTTP.

        Args:
            http: Cliente HTTP (tiempos, reintentos, 429).
        """
        self._http = http

    async def aclose(self) -> None:
        """Cierra las conexiones HTTP."""
        await self._http.aclose()

    async def fetch(self, feed: MediaFeed) -> tuple[ParseResult, int]:
        """Baja y lee un feed.

        Args:
            feed: Medio.

        Returns:
            Las notas leídas y los bytes descargados.

        Raises:
            FeedError: Si no es un RSS legible.
            ProviderError: Si el medio no responde.
        """
        response = await self._http.get(feed.url, {})
        return parse_feed(response.content, feed), len(response.content)
