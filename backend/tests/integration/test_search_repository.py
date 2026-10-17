"""Pipeline completo contra la base de pruebas: guardado real, IA y proveedores simulados.

Usa el mini-catálogo real (``geo_fixture``) para que las ubicaciones se
resuelvan con ``regions`` de verdad. Nada sale a internet ni gasta.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.gazetteer_repository import PostgresGazetteer
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.application.ports.llm import EnrichmentError
from app.application.ports.search_store import NewSearch, SearchConcept
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionLimits
from app.application.use_cases.extraction import ExtractTexts
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.run_search import PipelineLimits, RunSearch
from app.core.config import Settings
from app.domain.enrichment import Enrichment, LLMUsage
from app.domain.geocoding import Mention, MentionRole
from app.domain.queries import Provider
from app.domain.search import SearchStatus
from tests.integration.geo_fixture import load_fixture_catalog
from tests.unit.application.test_execute_queries import FakeCache, FakeLog
from tests.unit.application.test_run_search import (
    DEFAULT_REPLIES,
    IZTA_BODY,
    IZTA_LOCAL,
    IZTA_SEARCHAPI,
    LLM,
    MADRID,
    Extractor,
    Source,
    enrichment,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONCEPT_NAME = "Prueba pipeline"
# El mini-catálogo trae Francia, no España: la nota de fuera pasa en París.
REPLIES: dict[str, Enrichment | Exception] = {
    **DEFAULT_REPLIES,
    MADRID.title: enrichment(Mention("París", MentionRole.EVENT, country="Francia")),
}


def _clean(engine: Engine) -> None:
    with engine.begin() as conn:
        # Solo la base de pruebas: borrar búsquedas arrastra sus resultados y errores.
        conn.execute(text("DELETE FROM searches"))
        conn.execute(text("DELETE FROM articles"))
        conn.execute(text("DELETE FROM audit_log WHERE entity_type = 'search'"))
        conn.execute(text("DELETE FROM concepts WHERE name = :n"), {"n": CONCEPT_NAME})


@pytest.fixture(scope="module")
def catalog(settings: Settings, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    load_fixture_catalog(engine, settings, tmp_path_factory.mktemp("geodata"))
    yield engine
    engine.dispose()


@pytest.fixture
def concept_id(catalog: Engine) -> Iterator[int]:
    _clean(catalog)
    with catalog.begin() as conn:
        found = conn.execute(
            text(
                "INSERT INTO concepts (name, name_norm, description, keywords, color, created_by) "
                "VALUES (:n, 'PRUEBA PIPELINE', 'Cobro de piso', '{extorsión}', '#AA0000', "
                "'prueba') RETURNING id"
            ),
            {"n": CONCEPT_NAME},
        ).scalar_one()
    yield int(found)
    _clean(catalog)


@pytest.fixture
async def stores(
    test_engine: AsyncEngine, concept_id: int
) -> AsyncIterator[tuple[PostgresSearchStore, PostgresArticleStore]]:
    yield PostgresSearchStore(test_engine), PostgresArticleStore(test_engine)


async def new_search(store: PostgresSearchStore, engine: AsyncEngine, concept_id: int) -> UUID:
    async with engine.connect() as conn:
        cdmx = (await conn.execute(text("SELECT id FROM regions WHERE code = '09'"))).scalar_one()
    return await store.create(
        NewSearch(
            user_id="prueba",
            region_id=cdmx,
            date_from=date(2026, 10, 10),
            date_to=date(2026, 10, 16),
            concepts=(SearchConcept(concept_id, CONCEPT_NAME, "", ("extorsión",)),),
            queries_planned=2,
            credits_estimated=1,
        )
    )


def run_search(
    engine: AsyncEngine, searches: PostgresSearchStore, articles: PostgresArticleStore, llm: LLM
) -> RunSearch:
    sources = [
        Source(Provider.SEARCHAPI, [IZTA_SEARCHAPI, MADRID], cost=1),
        Source(Provider.LOCAL_INDEX, [IZTA_LOCAL]),
    ]
    providers = {s.provider: s for s in sources}
    gazetteer = PostgresGazetteer(engine)
    return RunSearch(
        searches=searches,
        articles=articles,
        regions=PostgresRegionRepository(engine),
        gazetteer=gazetteer,
        providers=providers,
        executor=ExecuteQueries(
            providers, FakeCache(), FakeLog(), ExecutionLimits(10, 0, {Provider.SEARCHAPI: 100})
        ),
        extractor=ExtractTexts(Extractor({IZTA_SEARCHAPI.url: IZTA_BODY}), 2),
        llm=llm,
        geocoder=GeocodeMentions(gazetteer),
        similarity=lambda a, b: 1.0 if a == b else 0.0,
        limits=PipelineLimits(150, 2, 0.10, 0.50),
    )


async def test_busqueda_guardada_de_punta_a_punta(
    test_engine: AsyncEngine,
    stores: tuple[PostgresSearchStore, PostgresArticleStore],
    concept_id: int,
) -> None:
    searches, articles = stores
    search_id = await new_search(searches, test_engine, concept_id)
    loaded = await searches.load(search_id)
    assert loaded is not None
    assert loaded.status is SearchStatus.PENDING
    assert [c.description for c in loaded.concepts] == ["Cobro de piso"]

    report = await run_search(test_engine, searches, articles, LLM(REPLIES)).run(search_id)

    assert report.status is SearchStatus.COMPLETED
    assert (report.articles, report.in_region, report.out_of_region) == (2, 1, 1)
    async with test_engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT status, credits_used, llm_tokens_in, llm_cost_usd, "
                        "results_count, started_at IS NOT NULL AS started, "
                        "finished_at IS NOT NULL AS finished, progress->>'stage' AS stage "
                        "FROM searches WHERE id = :id"
                    ),
                    {"id": search_id},
                )
            )
            .mappings()
            .one()
        )
        located = (
            await conn.execute(
                text(
                    "SELECT r.code, al.precision, al.is_primary, "
                    "ST_X(al.point) = ST_X(r.centroid) AS point_from_catalog "
                    "FROM article_locations al JOIN regions r ON r.id = al.region_id "
                    "JOIN articles a ON a.id = al.article_id "
                    "WHERE a.url_canonical = 'https://milenio.com/izta'"
                )
            )
        ).all()
        audit = (
            await conn.execute(
                text(
                    "SELECT payload->>'creditos', jsonb_array_length(payload->'consultas') "
                    "FROM audit_log WHERE entity_type = 'search' AND entity_id = :id"
                ),
                {"id": str(search_id)},
            )
        ).one()
        texts = (
            await conn.execute(
                text(
                    "SELECT a.extraction_status, length(t.body) > 300 FROM articles a "
                    "JOIN article_texts t ON t.article_id = a.id ORDER BY a.id"
                )
            )
        ).all()
    assert dict(row) == {
        "status": "completed",
        "credits_used": 1,
        "llm_tokens_in": 2000,
        "llm_cost_usd": Decimal("0.0003"),
        "results_count": 2,
        "started": True,
        "finished": True,
        "stage": "close",
    }
    assert [tuple(r) for r in located] == [("09007", "municipality", True, True)]
    assert tuple(audit) == ("1", 2)
    assert [tuple(t) for t in texts] == [("ok", True), ("fallback", False)]

    preview = await articles.preview(search_id, 5)
    assert next(p.place for p in preview) is not None
    first = preview[0]
    assert first.title == IZTA_SEARCHAPI.title
    assert first.in_region is True
    assert first.concepts == (CONCEPT_NAME,)
    assert first.precision == "municipality"
    assert {p.in_region for p in preview} == {True, False}
    status = await searches.progress_of(search_id)
    assert status is not None and status[0] is SearchStatus.COMPLETED


async def test_la_segunda_busqueda_reutiliza_lo_enriquecido(
    test_engine: AsyncEngine,
    stores: tuple[PostgresSearchStore, PostgresArticleStore],
    concept_id: int,
) -> None:
    searches, articles = stores
    first = await new_search(searches, test_engine, concept_id)
    await run_search(test_engine, searches, articles, LLM(REPLIES)).run(first)
    second = await new_search(searches, test_engine, concept_id)
    llm = LLM(REPLIES)

    report = await run_search(test_engine, searches, articles, llm).run(second)

    assert report.reused == 2
    assert llm.requests == []
    assert (report.in_region, report.out_of_region) == (1, 1)
    assert report.llm_cost_usd == 0


async def test_errores_fallo_inesperado_y_retencion_de_textos(
    test_engine: AsyncEngine,
    stores: tuple[PostgresSearchStore, PostgresArticleStore],
    concept_id: int,
) -> None:
    searches, articles = stores
    search_id = await new_search(searches, test_engine, concept_id)
    # Un mensaje enorme se recorta al guardarlo (MAX_ERROR_CHARS).
    failure = EnrichmentError("JSON inválido " + "x" * 3000, LLMUsage(10, 1))
    replies: dict[str, Enrichment | Exception] = {**REPLIES, MADRID.title: failure}

    await run_search(test_engine, searches, articles, LLM(replies)).run(search_id)
    await searches.fail(search_id, "El worker se cayó.")

    async with test_engine.connect() as conn:
        errors = (
            await conn.execute(
                text(
                    "SELECT stage, error_type, length(message), payload ? 'url' "
                    "FROM processing_errors WHERE search_id = :id"
                ),
                {"id": search_id},
            )
        ).all()
        failed = (
            await conn.execute(
                text("SELECT enrichment_status FROM articles WHERE url_canonical LIKE '%elpais%'")
            )
        ).scalar_one()
        final = (
            await conn.execute(
                text("SELECT status, error_summary FROM searches WHERE id = :id"),
                {"id": search_id},
            )
        ).one()
        await conn.execute(
            text("UPDATE article_texts SET extracted_at = now() - interval '40 days'")
        )
        await conn.commit()
    assert [tuple(e) for e in errors] == [("enrich", "EnrichmentError", 2000, True)]
    assert failed == "failed"
    assert tuple(final) == ("failed", "El worker se cayó.")
    assert await articles.purge_texts(30) == 2
    assert await articles.purge_texts(30) == 0
    assert await searches.load(UUID(int=0)) is None
