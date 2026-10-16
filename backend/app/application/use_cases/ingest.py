"""Ingesta periódica al índice local (ADR-0013).

Casos de uso que disparan el reloj de Celery (``celery beat``) y los
comandos ``make ingesta`` y ``make ingesta-historial``:

- ``IngestGdeltGkg``: baja el GKG translingual más reciente de GDELT (si no
  se procesó ya) y guarda las notas en español sobre México.
- ``IngestMediaRss``: lee los RSS de los medios **activos** de la lista
  curada y guarda sus notas.
- ``IngestGdeltNgrams``: baja los ngramas de GDELT (texto completo) de los
  minutos pendientes y guarda las notas en español que mencionan México.
- ``PurgeNewsIndex``: borra las notas más viejas que la retención y las
  frases del cuerpo más viejas que su propia retención (ADR-0014).
- ``PlanGdeltHistory``: mide los GKG de días anteriores **sin bajarlos**,
  para pedir permiso antes (los baja ``IngestGdeltGkg.run_file``).

Cada corrida queda en ``ingest_runs``, también si falla: una fuente caída no
detiene a las demás.

No hace: no busca en el índice (eso es el proveedor ``indice_local``).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.ports.ingest import (
    FeedSourcePort,
    GkgFile,
    GkgSourcePort,
    IngestRun,
    IngestRunLogPort,
    IngestSourceError,
    MediaFeed,
    NewsIndexPort,
    NgramsSourcePort,
    RunStatus,
)
from app.domain.errors import ProviderError
from app.domain.news_index import GDELT_NGRAMS_SOURCE, GDELT_SOURCE, NewsItem

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
        return await self.run_file(file)

    async def run_file(self, file: GkgFile) -> IngestReport:
        """Procesa un archivo concreto: el más reciente o uno del historial.

        Args:
            file: Archivo con tamaño y huella para verificarlo.

        Returns:
            El reporte. Un archivo ya procesado devuelve ``skipped`` sin
            bajarlo ni registrar nada.
        """
        started = self._clock()
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


class IngestGdeltNgrams:
    """Ingesta de los ngramas de GDELT: texto completo, por minuto (ADR-0014)."""

    def __init__(
        self,
        source: NgramsSourcePort,
        index: NewsIndexPort,
        runs: IngestRunLogPort,
        clock: Clock = _utc_now,
    ) -> None:
        """Recibe la fuente, el índice y el registro.

        Args:
            source: Archivos de ngramas de GDELT.
            index: Índice local.
            runs: Registro de corridas.
            clock: Reloj (las pruebas lo fijan).
        """
        self._source = source
        self._index = index
        self._runs = runs
        self._clock = clock

    async def run(self, minutes: Sequence[datetime]) -> list[IngestReport]:
        """Procesa los minutos que falten, en orden.

        Un minuto ya procesado no se mide ni se baja; uno que GDELT no
        publicó se salta sin registrar (es normal: publica en tandas).

        Args:
            minutes: Minutos a revisar (``recent_minutes``).

        Returns:
            Un reporte por minuto que se intentó bajar.
        """
        reports = []
        for moment in minutes:
            key = self._source.key_for(moment)
            if await self._runs.already_processed(key):
                continue
            started = self._clock()
            item = key.rsplit("/", 1)[-1]
            try:
                minute = await self._source.describe(moment)
                if minute is None:
                    continue
                result, size = await self._source.fetch(minute)
            except (ProviderError, IngestSourceError) as error:
                report = IngestReport(GDELT_NGRAMS_SOURCE, item, "error", message=str(error))
            else:
                new = await self._index.add(result.items)
                report = IngestReport(
                    GDELT_NGRAMS_SOURCE,
                    item,
                    "ok",
                    items_new=new,
                    items_kept=len(result.items),
                    items_seen=result.seen,
                    bytes_downloaded=size,
                    sample=result.items[:SAMPLE_SIZE],
                )
            reports.append(
                await _record(
                    self._runs, report, dedupe_key=key, started=started, finished=self._clock()
                )
            )
        return reports


def recent_minutes(now: datetime, lookback_minutes: int, delay_minutes: int) -> list[datetime]:
    """Minutos a revisar en una corrida de los ngramas, del más viejo al más nuevo.

    Args:
        now: Momento actual (con zona).
        lookback_minutes: Cuánto hacia atrás revisar (cubre el intervalo del
            reloj y algún retraso de GDELT).
        delay_minutes: Minutos recientes que se dejan para la siguiente
            corrida (GDELT recomienda pedir el archivo de hace 5 minutos).

    Returns:
        Un ``datetime`` por minuto, con segundos en cero.

    Example:
        >>> recent_minutes(datetime(2026, 10, 16, 23, 0, 30, tzinfo=UTC), 3, 1)
        [... 22:57, 22:58, 22:59]
    """
    last = now.replace(second=0, microsecond=0) - timedelta(minutes=delay_minutes)
    return [last - timedelta(minutes=back) for back in range(lookback_minutes - 1, -1, -1)]


@dataclass(frozen=True, slots=True)
class HistoryPlan:
    """Qué bajaría el historial, antes de bajar nada.

    Attributes:
        files: Archivos pendientes, del más nuevo al más viejo.
        already_done: Archivos que ya están en el índice.
        missing: Cuartos de hora que GDELT no tiene.
        failed: Archivos que no se pudieron medir, con el motivo.
    """

    files: tuple[GkgFile, ...]
    already_done: int
    missing: int
    failed: tuple[str, ...]

    @property
    def total_bytes(self) -> int:
        """Descarga total de los archivos pendientes."""
        return sum(file.size for file in self.files)


Progress = Callable[[int, int], None]


def _no_progress(done: int, total: int) -> None:
    return None


class PlanGdeltHistory:
    """Mide el historial de GDELT sin bajarlo, para pedir permiso antes (CLAUDE.md §2.6)."""

    def __init__(self, source: GkgSourcePort, runs: IngestRunLogPort) -> None:
        """Recibe la fuente y el registro.

        Args:
            source: Archivos GKG de GDELT.
            runs: Registro de corridas (para saltar lo ya procesado).
        """
        self._source = source
        self._runs = runs

    async def plan(self, urls: Sequence[str], on_progress: Progress = _no_progress) -> HistoryPlan:
        """Revisa cada archivo: ya procesado, inexistente o pendiente (con su tamaño).

        Args:
            urls: Direcciones candidatas, del más nuevo al más viejo.
            on_progress: Avisa ``(revisados, total)`` después de cada archivo.

        Returns:
            El plan. Un archivo que no se pudo medir queda en ``failed`` y
            no detiene a los demás.
        """
        files: list[GkgFile] = []
        failed: list[str] = []
        already_done = missing = 0
        for done, url in enumerate(urls, start=1):
            if await self._runs.already_processed(url):
                already_done += 1
            else:
                try:
                    file = await self._source.describe(url)
                except (ProviderError, IngestSourceError) as error:
                    failed.append(f"{url}: {error}")
                else:
                    if file is None:
                        missing += 1
                    else:
                        files.append(file)
            on_progress(done, len(urls))
        return HistoryPlan(tuple(files), already_done, missing, tuple(failed))


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


@dataclass(frozen=True, slots=True)
class PurgeReport:
    """Qué borró la limpieza diaria.

    Attributes:
        notes_deleted: Notas borradas por NEWS_INDEX_RETENTION_DAYS.
        bodies_cleared: Notas a las que se les quitaron las frases del cuerpo
            por NEWS_BODY_RETENTION_DAYS (la nota se queda).
    """

    notes_deleted: int
    bodies_cleared: int


class PurgeNewsIndex:
    """Borra del índice lo que ya pasó su retención."""

    def __init__(
        self,
        index: NewsIndexPort,
        retention_days: int,
        body_retention_days: int,
        clock: Clock = _utc_now,
    ) -> None:
        """Recibe el índice y las dos retenciones.

        Args:
            index: Índice local.
            retention_days: NEWS_INDEX_RETENTION_DAYS (la nota completa).
            body_retention_days: NEWS_BODY_RETENTION_DAYS (solo las frases
                del cuerpo, que son lo que más ocupa; ADR-0014).
            clock: Reloj.
        """
        self._index = index
        self._retention = timedelta(days=retention_days)
        self._body_retention = timedelta(days=body_retention_days)
        self._clock = clock

    async def run(self) -> PurgeReport:
        """Borra notas viejas y vacía las frases del cuerpo viejas.

        Returns:
            Cuántas notas se borraron y a cuántas se les quitó el cuerpo.
        """
        now = self._clock()
        deleted = await self._index.purge_before(now - self._retention)
        cleared = await self._index.clear_bodies_before(now - self._body_retention)
        return PurgeReport(deleted, cleared)
