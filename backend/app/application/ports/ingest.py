"""Puertos de la ingesta periódica al índice local (ADR-0013).

Las fuentes (archivos GKG de GDELT, RSS de medios) y el almacenamiento
(``news_index``, ``ingest_runs``) se implementan en ``adapters/``; los casos
de uso de ``application/use_cases/ingest.py`` los reciben sin saber de HTTP
ni de SQL.

No hace: no busca en el índice (eso es el proveedor ``indice_local``).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.domain.news_index import RSS_SOURCE_PREFIX, NewsItem

RunStatus = Literal["ok", "error", "skipped"]


class IngestSourceError(RuntimeError):
    """Una fuente respondió algo inutilizable (archivo incompleto, RSS roto...).

    Los adaptadores la especializan; los casos de uso la atrapan sin saber de
    formatos.
    """


@dataclass(frozen=True, slots=True)
class GkgFile:
    """Un archivo de GDELT con tamaño y huella (GKG o ngramas).

    Attributes:
        url: Dirección del ZIP.
        size: Tamaño en bytes que anuncia GDELT.
        md5: Huella MD5 que anuncia GDELT.
    """

    url: str
    size: int
    md5: str

    @property
    def name(self) -> str:
        """Nombre del archivo ("20261016191500.translation.gkg.csv.zip")."""
        return self.url.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Notas que salieron de un archivo o un feed.

    Attributes:
        items: Notas listas para el índice.
        seen: Filas o ``<item>`` leídos.
        discarded: Notas que debían entrar pero no se pudieron usar (sin
            título, URL web o fecha).
    """

    items: tuple[NewsItem, ...]
    seen: int
    discarded: int


@dataclass(frozen=True, slots=True)
class MediaFeed:
    """Un medio de la lista curada ``fuentes/medios_rss.csv``.

    Attributes:
        slug: Nombre corto (va en ``rss:<slug>``).
        name: Nombre del medio para mostrar.
        url: Dirección del RSS.
        active: Si se ingiere (solo tras revisar sus términos).
    """

    slug: str
    name: str
    url: str
    active: bool

    @property
    def source(self) -> str:
        """Origen en el índice: ``rss:la-jornada``."""
        return f"{RSS_SOURCE_PREFIX}{self.slug}"


@dataclass(frozen=True, slots=True)
class IngestRun:
    """Una corrida de la ingesta, para ``ingest_runs``.

    Attributes:
        source: ``gdelt_gkg`` o ``rss:<medio>``.
        item: Archivo o feed leído.
        dedupe_key: Archivo de GDELT (no se reprocesa); vacío en los feeds.
        status: ``ok``, ``error`` o ``skipped``.
        started_at: Inicio (UTC).
        finished_at: Fin (UTC).
        bytes_downloaded: Bytes bajados.
        items_seen: Filas o notas leídas.
        items_kept: Notas válidas para el índice.
        items_new: Notas que no estaban en el índice.
        error_message: Qué falló, en español.
    """

    source: str
    item: str
    dedupe_key: str | None
    status: RunStatus
    started_at: datetime
    finished_at: datetime
    bytes_downloaded: int = 0
    items_seen: int = 0
    items_kept: int = 0
    items_new: int = 0
    error_message: str | None = None


class GkgSourcePort(Protocol):
    """Archivos GKG de GDELT."""

    async def latest(self) -> GkgFile:
        """El archivo GKG que GDELT anuncia como el más reciente."""
        ...

    async def describe(self, url: str) -> GkgFile | None:
        """Mide un archivo anterior sin bajarlo (historial).

        Args:
            url: Dirección del archivo.

        Returns:
            El archivo con tamaño y huella, o ``None`` si GDELT no lo tiene.
        """
        ...

    async def fetch(self, file: GkgFile) -> tuple[ParseResult, int]:
        """Baja, verifica y lee un archivo.

        Args:
            file: Archivo anunciado.

        Returns:
            Las notas (solo español con México) y los bytes descargados.
        """
        ...


@dataclass(frozen=True, slots=True)
class NgramsMinute:
    """Un minuto de ngramas de GDELT: su índice de notas y sus frases (ADR-0014).

    Attributes:
        key: Identificador del minuto para no procesarlo dos veces (la URL
            del índice).
        toc: Índice de notas (``toc.json.gz``), con tamaño y huella.
        ngrams: Frases de 4 palabras (``ngrams.txt.gz``), con tamaño y huella.
    """

    key: str
    toc: GkgFile
    ngrams: GkgFile

    @property
    def size(self) -> int:
        """Bytes a descargar de los dos archivos."""
        return self.toc.size + self.ngrams.size


class NgramsSourcePort(Protocol):
    """Archivos de ngramas de GDELT, uno por minuto."""

    def key_for(self, moment: datetime) -> str:
        """Identificador del minuto, sin preguntar nada a GDELT.

        Args:
            moment: Minuto (con zona).

        Returns:
            La llave con la que ``ingest_runs`` lo recuerda.
        """
        ...

    async def describe(self, moment: datetime) -> NgramsMinute | None:
        """Mide los dos archivos de un minuto sin bajarlos.

        Args:
            moment: Minuto (con zona).

        Returns:
            El minuto, o ``None`` si GDELT no publicó ese minuto.
        """
        ...

    async def fetch(self, minute: NgramsMinute) -> tuple[ParseResult, int]:
        """Baja, verifica y lee un minuto.

        Args:
            minute: Minuto medido.

        Returns:
            Las notas en español que mencionan México y los bytes descargados.
        """
        ...


class FeedSourcePort(Protocol):
    """RSS de medios."""

    async def fetch(self, feed: MediaFeed) -> tuple[ParseResult, int]:
        """Baja y lee un feed.

        Args:
            feed: Medio.

        Returns:
            Las notas y los bytes descargados.
        """
        ...


class NewsIndexPort(Protocol):
    """Escritura y limpieza de ``news_index``."""

    async def add(self, items: Sequence[NewsItem]) -> int:
        """Guarda notas; las que ya estaban (misma URL) se ignoran.

        Args:
            items: Notas.

        Returns:
            Cuántas eran nuevas.
        """
        ...

    async def purge_before(self, cutoff: datetime) -> int:
        """Borra las notas publicadas antes de una fecha (retención).

        Args:
            cutoff: Fecha límite (UTC).

        Returns:
            Cuántas se borraron.
        """
        ...

    async def clear_bodies_before(self, cutoff: datetime) -> int:
        """Quita las frases del cuerpo de las notas publicadas antes de una fecha.

        Args:
            cutoff: Fecha límite (UTC).

        Returns:
            A cuántas notas se les quitaron.
        """
        ...


class IngestRunLogPort(Protocol):
    """Registro de corridas (``ingest_runs``)."""

    async def already_processed(self, dedupe_key: str) -> bool:
        """Dice si un archivo ya se procesó con éxito.

        Args:
            dedupe_key: Archivo (por ejemplo, la URL del GKG).

        Returns:
            ``True`` si ya hay una corrida exitosa con esa llave.
        """
        ...

    async def record(self, run: IngestRun) -> int:
        """Guarda una corrida.

        Args:
            run: La corrida.

        Returns:
            Su id, o 0 si otra corrida ya había registrado ese archivo como
            procesado.
        """
        ...
