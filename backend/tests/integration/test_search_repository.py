"""Pipeline completo contra la base de pruebas: guardado real, IA y proveedores simulados.

Usa el mini-catálogo real (``geo_fixture``) para que las ubicaciones se
resuelvan con ``regions`` de verdad. Nada sale a internet ni gasta.
"""

import argparse
import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.llm.factory import LLMSetup, MissingLLMKeyError
from app.adapters.persistence.gazetteer_repository import PostgresGazetteer
from app.adapters.persistence.regions_repository import PostgresRegionRepository
from app.adapters.persistence.search_repository import PostgresArticleStore, PostgresSearchStore
from app.application.ports.llm import EnrichmentError
from app.application.ports.search_store import NewSearch, SearchConcept
from app.application.use_cases.execute_queries import ExecuteQueries, ExecutionLimits
from app.application.use_cases.extraction import ExtractTexts
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.run_search import PipelineLimits, RunSearch
from app.cli import buscar, reubicar
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
    IZTA_MENTION,
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
    snapshot = await searches.snapshot(search_id)
    assert snapshot is not None
    assert (snapshot.status, snapshot.credits_used) == (SearchStatus.COMPLETED, 1)
    assert snapshot.llm_usage == LLMUsage(2000, 200)
    assert snapshot.progress["in_region"] == 1
    assert await searches.snapshot(UUID(int=0)) is None


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


def cli_settings(settings: Settings, **changes: object) -> Settings:
    """La configuración real, apuntando a la base de pruebas y sin SearchApi."""
    base: dict[str, object] = {
        "postgres_db": settings.postgres_test_db,
        "searchapi_api_key": None,
        "openai_api_key": SecretStr("llave-de-prueba"),
        "llm_provider": "openai",
    }
    return settings.model_copy(update={**base, **changes})


def cli_args(*extra: str) -> argparse.Namespace:
    return buscar.parse_args(["--concepto", CONCEPT_NAME, "--region", "09", *extra])


async def count_searches(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM searches"))).scalar_one())


async def test_el_comando_corre_aqui_y_muestra_el_resultado(
    test_engine: AsyncEngine,
    settings: Settings,
    concept_id: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ran: list[UUID] = []

    async def run_here(cfg: Settings, search_id: UUID) -> None:
        # En lugar de las piezas reales (red e IA), el pipeline con las simuladas.
        ran.append(search_id)
        searches = PostgresSearchStore(test_engine)
        await run_search(
            test_engine, searches, PostgresArticleStore(test_engine), LLM(REPLIES)
        ).run(search_id)

    with caplog.at_level(logging.INFO):
        code = await buscar.run(
            cli_args("--aqui"), cli_settings(settings), lambda _q: "si", run_here=run_here
        )

    assert code == 0
    assert len(ran) == 1
    text_ = caplog.text
    assert "Búsqueda (todavía no se ha gastado nada)" in text_
    assert "indice_local:" in text_
    assert "openai · gpt-6-luna" in text_
    assert "Búsqueda completed" in text_
    assert "Alcaldía Iztapalapa (municipio" in text_


async def test_el_comando_no_gasta_sin_un_si_ni_sin_llave(
    test_engine: AsyncEngine, settings: Settings, concept_id: int
) -> None:
    sent: list[UUID] = []

    cancelled = await buscar.run(
        cli_args(), cli_settings(settings), lambda _q: "no", enqueue=sent.append
    )
    no_key = await buscar.run(
        cli_args(), cli_settings(settings, openai_api_key=None), lambda _q: "si"
    )
    assert (cancelled, no_key) == (1, 1)
    assert sent == []
    assert await count_searches(test_engine) == 0


async def test_el_comando_manda_al_worker_y_espera(
    test_engine: AsyncEngine,
    settings: Settings,
    concept_id: int,
) -> None:
    searches = PostgresSearchStore(test_engine)
    queued: list[UUID] = []

    async def worker_finishes(_seconds: float) -> None:
        # Hace de worker: corre la búsqueda encolada en la primera pausa.
        if queued:
            await run_search(
                test_engine, searches, PostgresArticleStore(test_engine), LLM(REPLIES)
            ).run(queued.pop())

    code = await buscar.run(
        cli_args(),
        cli_settings(settings),
        lambda _q: "si",
        enqueue=queued.append,
        sleep=worker_finishes,
    )

    assert code == 0
    assert queued == []


async def test_el_comando_avisa_si_el_worker_no_responde(
    settings: Settings, concept_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(buscar, "wait_for", lambda *_a, **_k: asyncio.sleep(0, result=None))

    code = await buscar.run(
        cli_args(), cli_settings(settings), lambda _q: "si", enqueue=lambda _id: None
    )

    assert code == 1


async def test_las_pistas_se_guardan_y_se_reubica_sin_la_ia(
    test_engine: AsyncEngine,
    settings: Settings,
    stores: tuple[PostgresSearchStore, PostgresArticleStore],
    concept_id: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    searches, articles = stores
    search_id = await new_search(searches, test_engine, concept_id)
    await run_search(test_engine, searches, articles, LLM(REPLIES)).run(search_id)

    saved = {a.title: a for a in await articles.search_mentions(search_id)}
    izta = saved[IZTA_SEARCHAPI.title]
    assert izta.mentions == (IZTA_MENTION,)
    assert izta.primary_code == "09007"
    assert saved[MADRID.title].mentions[0].country == "Francia"
    # Una ubicación vieja equivocada (antes de corregir el catálogo).
    async with test_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE article_locations SET region_id = (SELECT id FROM regions "
                "WHERE code = '09'), precision = 'state' WHERE article_id = :a"
            ),
            {"a": izta.article_id},
        )
        await conn.execute(
            text("UPDATE search_results SET in_region = NULL WHERE article_id = :a"),
            {"a": izta.article_id},
        )

    with caplog.at_level(logging.INFO):
        code = await reubicar.run(
            reubicar.parse_args(["--busqueda", str(search_id)]), cli_settings(settings)
        )

    assert code == 0
    assert "1 de 2 notas cambiaron de ubicación" in caplog.text
    after = {a.title: a for a in await articles.search_mentions(search_id)}
    assert after[IZTA_SEARCHAPI.title].primary_code == "09007"
    async with test_engine.connect() as conn:
        inside = (
            await conn.execute(
                text("SELECT in_region FROM search_results WHERE article_id = :a"),
                {"a": izta.article_id},
            )
        ).scalars()
        # Una fila por proveedor que la encontró (SearchApi y el índice local).
        assert list(inside) == [True, True]
    snapshot = await searches.snapshot(search_id)
    assert snapshot is not None
    assert (snapshot.progress["in_region"], snapshot.progress["stage"]) == (1, "close")
    assert await searches.last_search_id() == search_id


async def test_reubicar_sin_busquedas(settings: Settings, concept_id: int) -> None:
    assert await reubicar.run(reubicar.parse_args([]), cli_settings(settings)) == 1


async def test_reprocesar_con_ia_desde_el_texto_guardado(
    test_engine: AsyncEngine,
    settings: Settings,
    stores: tuple[PostgresSearchStore, PostgresArticleStore],
    concept_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    searches, articles = stores
    search_id = await new_search(searches, test_engine, concept_id)
    await run_search(test_engine, searches, articles, LLM(REPLIES)).run(search_id)
    llm = LLM(REPLIES)
    monkeypatch.setattr(reubicar, "build_llm", lambda _s: LLMSetup("openai", llm, 0.10, 0.50))
    args = reubicar.parse_args(["--busqueda", str(search_id), "--con-ia"])

    cancelled = await reubicar.run(args, cli_settings(settings), lambda _q: "no")
    code = await reubicar.run(args, cli_settings(settings), lambda _q: "si")

    assert (cancelled, code) == (1, 0)
    assert len(llm.requests) == 2
    async with test_engine.connect() as conn:
        tokens = (
            await conn.execute(
                text("SELECT llm_tokens_in FROM searches WHERE id = :id"), {"id": search_id}
            )
        ).scalar_one()
        audit = (
            await conn.execute(
                text(
                    "SELECT payload->>'tokens_entrada' FROM audit_log "
                    "WHERE action = 'search.reprocessed' AND entity_id = :id"
                ),
                {"id": str(search_id)},
            )
        ).scalar_one()
    assert (tokens, audit) == (4000, "2000")

    def no_key(_s: Settings) -> LLMSetup:
        raise MissingLLMKeyError("Falta OPENAI_API_KEY en .env.")

    monkeypatch.setattr(reubicar, "build_llm", no_key)
    assert await reubicar.run(args, cli_settings(settings), lambda _q: "si") == 1
