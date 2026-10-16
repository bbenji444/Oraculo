"""Endpoints temporales /api/v1/local-index con piezas en memoria (ADR-0014)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.concepts import get_actor, get_concept_repository
from app.api.v1.local_index import get_index_stats, get_local_executor
from app.api.v1.regions import get_region_repository
from app.application.audit import Actor
from app.application.ports.local_index import IndexStats, SourceStats
from app.application.ports.provider_log import ProviderQueryRecord, QueryRun
from app.application.ports.providers import ProviderResponse
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionLimits
from app.domain.articles import RawArticle
from app.domain.queries import PlannedQuery, Provider
from app.main import create_app
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import IZTAPALAPA, FakeRegionRepository

CONCEPT: dict[str, Any] = {
    "name": "Ciberseguridad",
    "description": "",
    "keywords": ["hackeo"],
    "exclude_terms": ["curso"],
    "color": "#2e86de",
}
SEEN = datetime(2026, 10, 15, 18, 0, tzinfo=UTC)


def article(rank: int, source: str, day: int) -> RawArticle:
    return RawArticle.create(
        provider=Provider.LOCAL_INDEX,
        provider_rank=rank,
        url=f"https://medio.mx/{rank}",
        title=f"Hackeo {rank}",
        published_at=datetime(2026, 10, day, 18, 0, tzinfo=UTC),
        raw={"source": source, "gdelt_states": ["09"]},
    )


class FakeLocalIndex:
    def __init__(self) -> None:
        self.queries: list[PlannedQuery] = []

    @property
    def provider(self) -> Provider:
        return Provider.LOCAL_INDEX

    def is_configured(self) -> bool:
        return True

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        return {"palabras": "HACKEO"}

    def estimate_cost(self, query: PlannedQuery) -> int:
        return 0

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        self.queries.append(query)
        notes = (
            article(1, "gdelt_ngrams", 15),
            article(2, "gdelt_ngrams", 15),
            article(3, "gdelt_gkg", 14),
        )
        return ProviderResponse(notes, 200, {}, "[]")


class NoCache:
    async def get(self, key: str) -> tuple[RawArticle, ...] | None:
        return None

    async def set(self, key: str, articles: tuple[RawArticle, ...], ttl_seconds: int) -> None:
        raise AssertionError("El índice local no debe usar la caché")


class MemoryLog:
    def __init__(self) -> None:
        self.records: list[ProviderQueryRecord] = []

    async def record(self, entry: ProviderQueryRecord, actor: Actor | None = None) -> int:
        self.records.append(entry)
        return len(self.records)

    async def credits_used_since(self, provider: str, since: datetime) -> int:
        return 0

    async def runs_of(self, provider: str, query_text: str) -> list[QueryRun]:
        return []


class FakeStats:
    async def stats(self) -> IndexStats:
        return IndexStats(
            (SourceStats("gdelt_ngrams", 291, 291, 1_258_291, SEEN, SEEN),),
            total_bytes=21_810_380,
            last_run_at=SEEN,
        )


@pytest.fixture
def log() -> MemoryLog:
    return MemoryLog()


@pytest.fixture
def client(log: MemoryLog) -> Iterator[TestClient]:
    app: FastAPI = create_app()
    concepts, regions = FakeConceptRepository(), FakeRegionRepository()
    executor = ExecuteQueries(
        {Provider.LOCAL_INDEX: FakeLocalIndex()}, NoCache(), log, ExecutionLimits(10, 6, {})
    )
    stats = FakeStats()
    app.dependency_overrides[get_concept_repository] = lambda: concepts
    app.dependency_overrides[get_region_repository] = lambda: regions
    app.dependency_overrides[get_actor] = lambda: Actor("prueba", "127.0.0.1")
    app.dependency_overrides[get_local_executor] = lambda: executor
    app.dependency_overrides[get_index_stats] = lambda: stats
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_busca_un_concepto_en_el_indice_local_y_lo_registra(
    client: TestClient, log: MemoryLog
) -> None:
    concept_id = client.post("/api/v1/concepts", json=CONCEPT).json()["id"]

    response = client.get(
        "/api/v1/local-index/search",
        params={"concept_id": concept_id, "region_id": IZTAPALAPA.id, "days": 7},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["concept_name"] == "Ciberseguridad"
    assert body["region"] == "México › Ciudad de México › Iztapalapa"
    assert body["query_text"].startswith("contiene: hackeo · lugar: Iztapalapa")
    assert (body["status"], body["total"]) == ("ok", 3)
    assert body["notes"][0] == {
        "title": "Hackeo 1",
        "url": "https://medio.mx/1",
        "source_domain": "medio.mx",
        "published_at": "2026-10-15T18:00:00Z",
        "snippet": None,
        "source": "gdelt_ngrams",
        "gdelt_states": ["09"],
    }
    assert body["by_day"] == [{"label": "14/10", "count": 1}, {"label": "15/10", "count": 2}]
    assert body["by_source"] == [
        {"label": "gdelt_ngrams", "count": 2},
        {"label": "gdelt_gkg", "count": 1},
    ]
    # Queda en provider_queries como una búsqueda real, sin créditos.
    [record] = log.records
    assert (record.provider, record.cost_credits) == ("indice_local", 0)


def test_concepto_inexistente_es_404(client: TestClient) -> None:
    response = client.get(
        "/api/v1/local-index/search", params={"concept_id": 999, "region_id": IZTAPALAPA.id}
    )

    assert response.status_code == 404


def test_resumen_del_indice_en_megas(client: TestClient) -> None:
    body = client.get("/api/v1/local-index/stats").json()

    assert body["total_notes"] == 291
    assert body["total_mb"] == 20.8
    assert body["sources"][0]["body_mb"] == 1.2
    assert body["last_run_at"] == "2026-10-15T18:00:00Z"
