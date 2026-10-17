"""Lectura de los ngramas de GDELT: texto completo de las notas, por minuto (ADR-0014).

GDELT publica en ``https://data.gdeltproject.org/gdeltv5/weblegacy/ngrams/``,
por cada minuto con notas, dos archivos comprimidos con gzip:

- ``AAAAMMDDHHMM00.toc.json.gz``: una nota por línea, en JSON, con ``ID``,
  ``date``, ``lang``, ``title``, ``url`` e ``img``.
- ``AAAAMMDDHHMM00.ngrams.txt.gz``: ``ID``, frase de 4 palabras y veces que
  aparece, separados por tabulador. Los ``ID`` solo valen dentro del minuto.

Confirmado con el minuto real ``20261016224700`` (3,151 notas, 354 en
español, ~437 frases por nota). Documentación:
https://blog.gdeltproject.org/using-the-new-web-ngrams-dataset-to-find-relevant-coverage/

# VERIFICAR: GDELT presenta este conjunto como temporal y no publica un
# archivo "último" como el GKG. Los minutos salen en tandas: un minuto sin
# archivos responde 404 al HEAD, y eso es normal.

Términos (https://www.gdeltproject.org/about.html): uso sin restricción ni
costo, citando al GDELT Project con un link.

No hace: no guarda nada (eso es el caso de uso de ingesta) ni conserva el
texto: solo las frases normalizadas, para buscar.
"""

import gzip
import html
import json
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.adapters.ingest.gdelt_gkg import GkgFileError, measure, verify
from app.adapters.providers.http import ProviderHttpClient
from app.application.ports.ingest import NgramsMinute, ParseResult
from app.domain.names import normalize_name
from app.domain.news_index import (
    GDELT_NGRAMS_SOURCE,
    InvalidNewsError,
    MexicoMentions,
    NewsItem,
)

NGRAMS_BASE_URL = "https://data.gdeltproject.org/gdeltv5/weblegacy/ngrams/"
TOC_SUFFIX = ".toc.json.gz"
NGRAMS_SUFFIX = ".ngrams.txt.gz"
# Código de idioma del TOC (ISO 639-1), distinto del "spa" del GKG.
SPANISH_ISO = "es"
_STAMP_FORMAT = "%Y%m%d%H%M00"
# Columnas del archivo de frases: ID, frase, veces.
_NGRAM_FIELDS = 3


@dataclass(frozen=True, slots=True)
class TocEntry:
    """Una nota del índice de un minuto.

    Attributes:
        doc_id: ``ID`` dentro del minuto.
        url: Link a la nota.
        title: Título, ya sin entidades HTML (puede venir vacío).
        language: Código ISO del idioma (``es``).
        published_at: Fecha que reporta GDELT (UTC), si se pudo leer.
    """

    doc_id: int
    url: str
    title: str
    language: str
    published_at: datetime | None


def minute_stamp(moment: datetime) -> str:
    """Nombre del minuto en los archivos de GDELT (``20261016224700``).

    Args:
        moment: Minuto con zona.

    Returns:
        El sello en UTC, con los segundos en cero.
    """
    return moment.astimezone(UTC).strftime(_STAMP_FORMAT)


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def parse_toc(data: bytes) -> list[TocEntry]:
    """Lee el índice de notas de un minuto (``toc.json.gz`` ya descomprimido).

    Args:
        data: Texto JSON, una nota por línea.

    Returns:
        Las notas legibles. Una línea rota se ignora: no debe tirar el minuto.
    """
    entries = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
            doc_id = int(record["ID"])
        except (ValueError, KeyError, TypeError):
            continue
        entries.append(
            TocEntry(
                doc_id=doc_id,
                url=str(record.get("url") or ""),
                title=html.unescape(str(record.get("title") or "")),
                language=str(record.get("lang") or ""),
                published_at=_date(record.get("date")),
            )
        )
    return entries


def parse_ngrams(data: bytes, wanted: set[int]) -> dict[int, list[str]]:
    """Junta las frases de las notas que interesan (``ngrams.txt.gz`` descomprimido).

    Args:
        data: Texto con ``ID<TAB>frase<TAB>veces`` por línea.
        wanted: ``ID`` de las notas que interesan (las de español).

    Returns:
        Las frases de cada nota, en el orden del archivo.
    """
    phrases: dict[int, list[str]] = {doc_id: [] for doc_id in wanted}
    for line in data.decode("utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) != _NGRAM_FIELDS or not parts[0].isdigit():
            continue
        doc_id = int(parts[0])
        if doc_id in wanted:
            phrases[doc_id].append(parts[1])
    return phrases


def build_items(
    entries: Sequence[TocEntry],
    phrases: dict[int, list[str]],
    mentions: MexicoMentions,
) -> ParseResult:
    """Arma las notas del índice: español que menciona México.

    Args:
        entries: Notas del minuto.
        phrases: Frases por nota (solo las de español).
        mentions: Reconocedor de "menciona México" (estados del catálogo).

    Returns:
        Las notas, cuántas se vieron y cuántas eran de México pero no se
        pudieron usar (sin título, URL web o fecha).
    """
    items: list[NewsItem] = []
    discarded = 0
    for entry in entries:
        if entry.language != SPANISH_ISO:
            continue
        body = phrases.get(entry.doc_id, [])
        try:
            item = NewsItem.create(
                source=GDELT_NGRAMS_SOURCE,
                url=entry.url,
                title=entry.title,
                published_at=entry.published_at,
                language=entry.language,
                body_phrases=body,
            )
        except InvalidNewsError:
            # Sin título no se puede mostrar; solo cuenta si era de México.
            if mentions.found_in(normalize_name(" ".join(body))):
                discarded += 1
            continue
        if mentions.found_in(f"{item.text_norm} {item.body_terms or ''}", item.source_domain):
            items.append(item)
    return ParseResult(tuple(items), seen=len(entries), discarded=discarded)


def _gunzip(data: bytes, name: str) -> bytes:
    try:
        return gzip.decompress(data)
    except (OSError, EOFError, zlib.error) as error:
        raise GkgFileError(f"{name}: el archivo comprimido está dañado.") from error


class GdeltNgramsSource:
    """Mide, baja y lee los ngramas de GDELT, un minuto a la vez."""

    def __init__(self, http: ProviderHttpClient, mentions: MexicoMentions) -> None:
        """Recibe el cliente HTTP y el filtro de México.

        Args:
            http: Cliente HTTP (tiempos, reintentos, 429).
            mentions: Reconocedor de "menciona México".
        """
        self._http = http
        self._mentions = mentions

    async def aclose(self) -> None:
        """Cierra las conexiones HTTP."""
        await self._http.aclose()

    def key_for(self, moment: datetime) -> str:
        """Ver ``NgramsSourcePort.key_for``: la URL del índice del minuto."""
        return f"{NGRAMS_BASE_URL}{minute_stamp(moment)}{TOC_SUFFIX}"

    async def describe(self, moment: datetime) -> NgramsMinute | None:
        """Ver ``NgramsSourcePort.describe``.

        El ETag del servidor de archivos de GDELT es el MD5 (medido el
        16/10/2026, ADR-0014); con él se verifica cada descarga.

        Raises:
            GkgFileError: Si la respuesta no trae tamaño y MD5 usables.
            ProviderError: Si GDELT no responde.
        """
        stamp = minute_stamp(moment)
        toc = await measure(self._http, f"{NGRAMS_BASE_URL}{stamp}{TOC_SUFFIX}")
        if toc is None:
            return None
        ngrams = await measure(self._http, f"{NGRAMS_BASE_URL}{stamp}{NGRAMS_SUFFIX}")
        if ngrams is None:
            return None
        return NgramsMinute(toc.url, toc, ngrams)

    async def fetch(self, minute: NgramsMinute) -> tuple[ParseResult, int]:
        """Ver ``NgramsSourcePort.fetch``.

        Raises:
            GkgFileError: Si un archivo llegó incompleto o dañado.
            ProviderError: Si GDELT no responde.
        """
        toc_raw = (await self._http.get(minute.toc.url, {})).content
        verify(toc_raw, minute.toc)
        entries = parse_toc(_gunzip(toc_raw, minute.toc.name))
        spanish = {entry.doc_id for entry in entries if entry.language == SPANISH_ISO}
        ngrams_raw = (await self._http.get(minute.ngrams.url, {})).content
        verify(ngrams_raw, minute.ngrams)
        phrases = parse_ngrams(_gunzip(ngrams_raw, minute.ngrams.name), spanish)
        return build_items(entries, phrases, self._mentions), len(toc_raw) + len(ngrams_raw)
