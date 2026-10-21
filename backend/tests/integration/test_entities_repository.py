"""Repositorio de entidades contra la base de pruebas (Fase 9.4, decisión D6).

Comprueba lo que solo la base puede garantizar: que las propuestas se agrupan
dentro del caso y nunca entre casos ni con algo ya revisado, que volver a
agregar una nota no duplica la evidencia, que los lugares toman la región ya
ubicada y que revisar firma y deja bitácora.
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.entities_repository import PostgresEntityRepository
from app.application.audit import Actor, AuditEntry
from app.application.ports.entities import FailedExtraction, StoredExtraction
from app.core.config import Settings
from app.domain.enrichment import LLMUsage
from app.domain.entity_extraction import (
    AnalyzedText,
    CaseArticleEntitiesStatus,
    RawProposal,
    TextSource,
    review_proposals,
)
from app.domain.investigation import InvestigationAction, LegalStatus, ReviewStatus
from tests.integration.test_pipeline_tables import region_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

BACKEND_DIR = Path(__file__).resolve().parents[2]
BENJI = Actor("benji")
BODY = (
    "Un juez giró orden de aprehensión contra Julián Ortega Ruiz por el homicidio de "
    "Ramón Salas en la colonia Polanco."
)
PERSON = RawProposal(
    "person",
    "Julián Ortega Ruiz",
    (),
    "event",
    "alleged",
    0.9,
    "orden de aprehensión contra Julián Ortega Ruiz",
)
PLACE = RawProposal("place", "Polanco", (), "event", None, 0.8, "en la colonia Polanco")


@pytest.fixture(scope="module")
def sync_engine(settings: Settings) -> Iterator[Engine]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ALEMBIC_TARGET", "test")
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean(sync_engine: Engine) -> Iterator[None]:
    yield
    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM cases"))
        conn.execute(text("DELETE FROM entities"))
        conn.execute(text("DELETE FROM articles WHERE url_canonical LIKE 'https://entidades.mx/%'"))
        conn.execute(text("DELETE FROM audit_log WHERE entity_type = 'case'"))


def new_case(engine: Engine) -> UUID:
    with engine.begin() as conn:
        return UUID(
            str(
                conn.execute(
                    text(
                        "INSERT INTO cases (name, name_norm, created_by) "
                        "VALUES ('Caso', 'CASO', 'benji') RETURNING id"
                    )
                ).scalar_one()
            )
        )


def new_article(engine: Engine, case_id: UUID, *, polanco_region: int | None = None) -> int:
    with engine.begin() as conn:
        article = int(
            conn.execute(
                text(
                    "INSERT INTO articles (url_canonical, url_hash, title, title_norm, "
                    "extraction_status) VALUES (:url, md5(:url), 'Orden en Polanco', "
                    "'ORDEN EN POLANCO', 'ok') RETURNING id"
                ),
                {"url": f"https://entidades.mx/{uuid4()}"},
            ).scalar_one()
        )
        conn.execute(
            text("INSERT INTO article_texts (article_id, body) VALUES (:a, :b)"),
            {"a": article, "b": BODY},
        )
        if polanco_region is not None:
            conn.execute(
                text(
                    "INSERT INTO article_locations (article_id, mention_text, role, region_id, "
                    "precision, confidence) VALUES (:a, 'colonia Polanco', 'event', :r, "
                    "'locality', 0.9)"
                ),
                {"a": article, "r": polanco_region},
            )
        add_to_case(conn, case_id, article)
    return article


def add_to_case(conn: Connection, case_id: UUID, article: int) -> None:
    conn.execute(
        text("INSERT INTO case_articles (case_id, article_id, added_by) VALUES (:c, :a, 'benji')"),
        {"c": case_id, "a": article},
    )


def extraction(article: int, *proposals: RawProposal) -> StoredExtraction:
    text_ = AnalyzedText("Orden en Polanco", BODY, TextSource.FULL_TEXT)
    return StoredExtraction(
        article,
        "entities_v1",
        "gpt-6-luna",
        TextSource.FULL_TEXT,
        review_proposals(proposals, text_),
        LLMUsage(2000, 500),
        0.00045,
    )


def audit() -> AuditEntry:
    return AuditEntry(BENJI, InvestigationAction.CASE_ENTITIES_EXTRACTED, {"status": "ok"})


async def test_la_misma_persona_en_dos_notas_es_una_sugerencia_con_dos_menciones(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    first, second = new_article(sync_engine, case_id), new_article(sync_engine, case_id)

    for article in (first, second):
        stored = extraction(article, PERSON)
        await repo.save_extraction(stored)
        await repo.materialize(case_id, stored, 0.00045, audit())

    [entity] = await repo.list_entities(case_id, ReviewStatus.SUGGESTED)
    assert entity.label == "Julián Ortega Ruiz"
    assert entity.article_count == 2
    assert entity.suggested_legal_status is LegalStatus.ALLEGED
    analysis = await repo.analysis(case_id)
    assert (analysis.done, analysis.pending) == (2, 0)
    assert analysis.cost_usd == pytest.approx(0.0009)
    assert await repo.get_extraction(first, "entities_v1") is not None


async def test_nada_se_junta_entre_casos(sync_engine: Engine, test_engine: AsyncEngine) -> None:
    repo = PostgresEntityRepository(test_engine)
    one, two = new_case(sync_engine), new_case(sync_engine)
    article = new_article(sync_engine, one)
    with sync_engine.begin() as conn:
        add_to_case(conn, two, article)
    stored = extraction(article, PERSON)

    await repo.materialize(one, stored, 0.00045, audit())
    await repo.materialize(two, stored, 0.0, audit())

    [a] = await repo.list_entities(one, ReviewStatus.SUGGESTED)
    [b] = await repo.list_entities(two, ReviewStatus.SUGGESTED)
    assert a.entity_id != b.entity_id


async def test_volver_a_agregar_la_nota_no_duplica_la_evidencia(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    article = new_article(sync_engine, case_id)
    stored = extraction(article, PERSON)
    await repo.materialize(case_id, stored, 0.0, audit())

    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM case_articles WHERE article_id = :a"), {"a": article})
    # Sin la nota, la sugerencia no se ve; al regresar, vuelve sin duplicarse.
    assert await repo.list_entities(case_id, ReviewStatus.SUGGESTED) == []
    with sync_engine.begin() as conn:
        add_to_case(conn, case_id, article)
    result = await repo.materialize(case_id, stored, 0.0, audit())

    assert result is not None
    assert result.skipped == 1
    [entity] = await repo.list_entities(case_id, ReviewStatus.SUGGESTED)
    assert len(entity.mentions) == 1


async def test_lo_confirmado_no_recibe_menciones_nuevas_solas(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    first, second = new_article(sync_engine, case_id), new_article(sync_engine, case_id)
    await repo.materialize(case_id, extraction(first, PERSON), 0.0, audit())
    [entity] = await repo.list_entities(case_id, ReviewStatus.SUGGESTED)
    confirm = AuditEntry(BENJI, InvestigationAction.ENTITY_CONFIRMED, {"entity_id": 1})

    reviewed = await repo.review(
        case_id,
        entity.entity_id,
        status=ReviewStatus.CONFIRMED,
        legal_status=LegalStatus.ALLEGED,
        reviewer="benji",
        audit=confirm,
    )
    await repo.materialize(case_id, extraction(second, PERSON), 0.0, audit())

    assert (reviewed.review_status, reviewed.reviewed_by) == (ReviewStatus.CONFIRMED, "benji")
    assert reviewed.reviewed_at is not None
    # La nota nueva propone otra sugerencia (la 9.5 propondrá unirlas).
    assert len(await repo.list_entities(case_id, ReviewStatus.SUGGESTED)) == 1
    counts = await repo.review_counts(case_id)
    assert (counts[ReviewStatus.CONFIRMED], counts[ReviewStatus.SUGGESTED]) == (1, 1)
    with sync_engine.connect() as conn:
        actions = (
            conn.execute(
                text("SELECT action FROM audit_log WHERE entity_id = :c ORDER BY id"),
                {"c": str(case_id)},
            )
            .scalars()
            .all()
        )
    assert actions == ["case.entities_extracted", "entity.confirmed", "case.entities_extracted"]


async def test_un_lugar_toma_la_region_que_ya_ubico_la_nota(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    with sync_engine.begin() as conn:
        region = region_id(conn)
    article = new_article(sync_engine, case_id, polanco_region=region)
    place = RawProposal(
        "place", "Polanco", ("colonia Polanco",), "event", None, 0.8, "en la colonia Polanco"
    )

    await repo.materialize(case_id, extraction(article, place), 0.0, audit())

    [entity] = await repo.list_entities(case_id, ReviewStatus.SUGGESTED)
    assert entity.region_id == region
    assert entity.aliases == ("colonia Polanco",)


async def test_una_falla_se_cobra_y_se_puede_volver_a_pedir(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    article = new_article(sync_engine, case_id)
    failure = FailedExtraction(
        article,
        "entities_v1",
        "gpt-6-luna",
        TextSource.FULL_TEXT,
        LLMUsage(3000, 10),
        0.0003,
        "JSON inválido",
    )

    await repo.save_failure(case_id, failure, audit())
    assert await repo.to_analyze(case_id, 10) == [article]
    assert await repo.get_extraction(article, "entities_v1") is None
    await repo.save_extraction(extraction(article, PERSON))

    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, tokens_in FROM entity_extractions WHERE article_id = :a"),
            {"a": article},
        ).one()
    # Lo gastado en el intento fallido se suma al bueno.
    assert (row.status, row.tokens_in) == ("ok", 5000)
    source = await repo.article_source(case_id, article)
    assert source is not None
    assert (source.status, source.full_text, source.stored_body) == (
        CaseArticleEntitiesStatus.FAILED,
        True,
        BODY,
    )
    await repo.set_status(case_id, [article], CaseArticleEntitiesStatus.QUEUED)
    assert (await repo.analysis(case_id)).queued == 1
