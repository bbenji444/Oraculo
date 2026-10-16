"""Ingesta periódica al índice local (ADR-0013).

Tres casos de uso que dispara el reloj de Celery (``celery beat``) y el
comando ``make ingesta``:

- ``IngestGdeltGkg``: baja el GKG translingual más reciente de GDELT (si no
  se procesó ya) y guarda las notas en español sobre México.
- ``IngestMediaRss``: lee los RSS de los medios **activos** de la lista
  curada y guarda sus notas.
- ``PurgeNewsIndex``: borra las notas más viejas que la retención.

Cada corrida queda en ``ingest_runs``, también si falla: una fuente caída no
detiene a las demás.

No hace: no busca en el índice (eso es el proveedor ``indice_local``).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.ports.ingest import (
    FeedSourcePort,
    GkgSourcePort,
    IngestRun,
    IngestRunLogPort,
    IngestSourceError,
    MediaFeed,
    NewsIndexPort,
    RunStatus,
)
from app.domain.errors import ProviderError
from app.domain.news_index import GDELT_SOURCE, NewsItem

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class IngestReport:
    """Qué pasó en una corrida, para el registro y para mostrar.

    Attributes:
        source: ``gdelt_gkg`` o ``rss:<medio>``.
        item: Archivo o feed.
        status: ``ok``, ``error`` o ``skipped``.
        items_new: Notas nuevas en el índice.
        items_kept: Notas válidas leídas.
        items_seen: Filas o notas leídas.
        bytes_downloaded: Bytes bajados.
        message: Motivo si falló o se saltó.
        sample: Algunas notas leídas, para mostrar ejemplos reales.
    """

    source: str
    item: str
    status: RunStatus
    items_new: int = 0
    items_kept: int = 0
    items_seen: int = 0
    bytes_downloaded: int = 0
    message: str | None = None
    sample: tuple[NewsItem, ...] = ()


# Notas que se guardan en el reporte para mostrar ejemplos (CLAUDE.md §2.6).
SAMPLE_SIZE = 5


async def _record(
    runs: IngestRunLogPort,
    report: IngestReport,
    *,
    dedupe_key: str | None,
    started: datetime,
    finished: datetime,
) -> IngestReport:
    await runs.record(
        IngestRun(
            source=report.source,
            item=report.item,
            dedupe_key=dedupe_key,
            status=report.status,
            started_at=started,
            finished_at=finished,
            bytes_downloaded=report.bytes_downloaded,
            items_seen=report.items_seen,
            items_kept=report.items_kept,
            items_new=report.items_new,
            error_message=report.message,
        )
    )
    return report


class IngestGdeltGkg:
    """Ingesta del archivo GKG más reciente de GDELT."""

    def __init__(
        self,
        source: GkgSourcePort,
        index: NewsIndexPort,
        runs: IngestRunLogPort,
        clock: Clock = _utc_now,
    ) -> None:
        """Recibe la fuente, el índice y el registro.

        Args:
            source: Archivos GKG de GDELT.
            index: Índice local.
            runs: Registro de corridas.
            clock: Reloj (las pruebas lo fijan).
        """
        self._source = source
        self._index = index
        self._runs = runs
        self._clock = clock

    async def run(self) -> IngestReport:
        """Procesa el archivo más reciente si no se procesó ya.

        Returns:
            El reporte de la corrida. Un archivo ya procesado devuelve
            ``skipped`` sin registrar nada (pasa cuando la corrida anterior
            ya lo tomó).
        """
        started = self._clock()
        try:
            file = await self._source.latest()
        except (ProviderError, IngestSourceError) as error:
            report = IngestReport(
                GDELT_SOURCE, "lastupdate-translation.txt", "error", message=str(error)
            )
            return await _record(
                self._runs, report, dedupe_key=None, started=started, finished=self._clock()
            )
        if await self._runs.already_processed(file.url):
            return IngestReport(GDELT_SOURCE, file.name, "skipped", message="Ya procesado.")
        try:
            result, size = await self._source.fetch(file)
        except (ProviderError, IngestSourceError) as error:
            report = IngestReport(GDELT_SOURCE, file.name, "error", message=str(error))
            return await _record(
                self._runs, report, dedupe_key=file.url, started=started, finished=self._clock()
            )
        new = await self._index.add(result.items)
        report = IngestReport(
            GDELT_SOURCE,
            file.name,
            "ok",
            items_new=new,
            items_kept=len(result.items),
            items_seen=result.seen,
            bytes_downloaded=size,
            sample=result.items[:SAMPLE_SIZE],
        )
        return await _record(
            self._runs, report, dedupe_key=file.url, started=started, finished=self._clock()
        )


class IngestMediaRss:
    """Ingesta de los RSS de los medios activos."""

    def __init__(
        self,
        source: FeedSourcePort,
        feeds: Sequence[MediaFeed],
        index: NewsIndexPort,
        runs: IngestRunLogPort,
        clock: Clock = _utc_now,
    ) -> None:
        """Recibe la fuente, la lista de medios, el índice y el registro.

        Args:
            source: Lector de RSS.
            feeds: Lista curada; solo se leen los activos.
            index: Índice local.
            runs: Registro de corridas.
            clock: Reloj.
        """
        self._source = source
        self._feeds = [feed for feed in feeds if feed.active]
        self._index = index
        self._runs = runs
        self._clock = clock

    async def run(self) -> list[IngestReport]:
        """Lee cada medio activo; si uno falla, los demás siguen.

        Returns:
            Un reporte por medio activo (vacío si no hay ninguno).
        """
        reports = []
        for feed in self._feeds:
            started = self._clock()
            try:
                result, size = await self._source.fetch(feed)
            except (ProviderError, IngestSourceError) as error:
                report = IngestReport(feed.source, feed.url, "error", message=str(error))
            else:
                new = await self._index.add(result.items)
                report = IngestReport(
                    feed.source,
                    feed.url,
                    "ok",
                    items_new=new,
                    items_kept=len(result.items),
                    items_seen=result.seen,
                    bytes_downloaded=size,
                    sample=result.items[:SAMPLE_SIZE],
                )
            reports.append(
                await _record(
                    self._runs, report, dedupe_key=None, started=started, finished=self._clock()
                )
            )
        return reports


class PurgeNewsIndex:
    """Borra del índice las notas más viejas que la retención."""

    def __init__(self, index: NewsIndexPort, retention_days: int, clock: Clock = _utc_now) -> None:
        """Recibe el índice y la retención.

        Args:
            index: Índice local.
            retention_days: ``NEWS_INDEX_RETENTION_DAYS``.
            clock: Reloj.
        """
        self._index = index
        self._retention = timedelta(days=retention_days)
        self._clock = clock

    async def run(self) -> int:
        """Borra lo publicado antes de hoy menos la retención.

        Returns:
            Cuántas notas se borraron.
        """
        return await self._index.purge_before(self._clock() - self._retention)
