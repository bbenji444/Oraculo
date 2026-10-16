"""Fuentes, índice y registro falsos para probar la ingesta sin red ni base."""

from collections.abc import Sequence
from datetime import UTC, datetime

from app.application.ports.ingest import GkgFile, IngestRun, ParseResult
from app.domain.news_index import NewsItem

NOW = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)
FILE = GkgFile(
    "https://data.gdeltproject.org/gdeltv2/20261016194500.translation.gkg.csv.zip", 10, "x"
)


def news(n: int, source: str = "gdelt_gkg") -> NewsItem:
    return NewsItem.create(
        source=source,
        url=f"https://medio.mx/nota-{n}",
        title=f"Nota {n}",
        published_at=NOW,
    )


def parsed(count: int, source: str = "gdelt_gkg") -> ParseResult:
    return ParseResult(tuple(news(n, source) for n in range(count)), seen=count * 3, discarded=0)


class FakeIndex:
    def __init__(self) -> None:
        self.urls: set[str] = set()
        self.cutoff: datetime | None = None

    async def add(self, items: Sequence[NewsItem]) -> int:
        new = {item.url for item in items} - self.urls
        self.urls |= new
        return len(new)

    async def purge_before(self, cutoff: datetime) -> int:
        self.cutoff = cutoff
        return 7


class FakeRuns:
    def __init__(self, processed: Sequence[str] = ()) -> None:
        self.processed = set(processed)
        self.runs: list[IngestRun] = []

    async def already_processed(self, dedupe_key: str) -> bool:
        return dedupe_key in self.processed

    async def record(self, run: IngestRun) -> int:
        self.runs.append(run)
        if run.status == "ok" and run.dedupe_key:
            self.processed.add(run.dedupe_key)
        return len(self.runs)


class FakeGkg:
    def __init__(self, result: ParseResult | Exception, latest: GkgFile | Exception = FILE) -> None:
        self.result = result
        self.announced = latest
        self.fetched = 0

    async def latest(self) -> GkgFile:
        if isinstance(self.announced, Exception):
            raise self.announced
        return self.announced

    async def fetch(self, file: GkgFile) -> tuple[ParseResult, int]:
        self.fetched += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result, 8_000_000
