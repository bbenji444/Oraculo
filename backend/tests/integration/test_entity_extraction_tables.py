"""Reglas de la migración 0020 que garantiza la base (Fase 9.4, ADR-0103).

Cada valor de los enums de ``app.domain.entity_extraction`` debe pasar el
CHECK de su columna; una extracción se guarda una vez por nota y versión de
prompt, y una mención no se repite.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.domain.entity_extraction import CaseArticleEntitiesStatus, ExtractionState, TextSource
from tests.integration.test_investigation_tables import new_case, new_entity, new_mention
from tests.integration.test_pipeline_tables import new_article

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def conn(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Iterator[Connection]:
    monkeypatch.setenv("ALEMBIC_TARGET", "test")
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(settings.database_url(test=True))
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()
    engine.dispose()


_EXTRACTION = text(
    "INSERT INTO entity_extractions (article_id, prompt_version, status, model, source, output) "
    "VALUES (:article, :version, :status, 'gpt-6-luna', :source, CAST(:output AS jsonb))"
)


def add_case_article(conn: Connection, case: str, article: int) -> None:
    conn.execute(
        text("INSERT INTO case_articles (case_id, article_id, added_by) VALUES (:c, :a, 'benji')"),
        {"c": case, "a": article},
    )


def test_una_nota_del_caso_nace_pendiente_y_sin_costo(conn: Connection) -> None:
    case, article = new_case(conn), new_article(conn)
    add_case_article(conn, case, article)

    row = conn.execute(
        text("SELECT entities_status, entities_cost_usd FROM case_articles WHERE case_id = :c"),
        {"c": case},
    ).one()

    assert row.entities_status == CaseArticleEntitiesStatus.PENDING
    assert float(row.entities_cost_usd) == 0


def test_cada_estado_de_analisis_del_dominio_pasa_su_check(conn: Connection) -> None:
    case, article = new_case(conn), new_article(conn)
    add_case_article(conn, case, article)
    update = text("UPDATE case_articles SET entities_status = :s WHERE case_id = :c")

    for status in CaseArticleEntitiesStatus:
        conn.execute(update, {"s": status, "c": case})
    with pytest.raises(IntegrityError, match="case_articles_entities_status_known"):
        conn.execute(update, {"s": "running", "c": case})


def test_cada_estado_y_origen_de_extraccion_pasa_su_check(conn: Connection) -> None:
    for number, (state, source) in enumerate((s, t) for s in ExtractionState for t in TextSource):
        conn.execute(
            _EXTRACTION,
            {
                "article": new_article(conn, f"https://medio.mx/extraccion-{number}"),
                "version": "entities_v1",
                "status": state,
                "source": source,
                "output": '{"entities": []}' if state is ExtractionState.OK else None,
            },
        )

    with pytest.raises(IntegrityError, match="entity_extractions_source_known"):
        conn.execute(
            _EXTRACTION,
            {
                "article": new_article(conn, "https://medio.mx/resumen"),
                "version": "entities_v1",
                "status": "ok",
                "source": "summary",
                "output": "{}",
            },
        )


def test_una_extraccion_correcta_lleva_su_salida_y_una_fallida_no(conn: Connection) -> None:
    article = new_article(conn)
    params = {"article": article, "version": "entities_v1", "source": TextSource.FULL_TEXT}

    with (
        pytest.raises(IntegrityError, match="entity_extractions_output_when_ok"),
        conn.begin_nested(),
    ):
        conn.execute(_EXTRACTION, {**params, "status": "ok", "output": None})
    with pytest.raises(IntegrityError, match="entity_extractions_output_when_ok"):
        conn.execute(_EXTRACTION, {**params, "status": "failed", "output": "{}"})


def test_una_extraccion_por_nota_y_version_de_prompt(conn: Connection) -> None:
    article = new_article(conn)
    params = {
        "article": article,
        "status": "ok",
        "source": TextSource.FULL_TEXT,
        "output": '{"entities": []}',
    }
    conn.execute(_EXTRACTION, {**params, "version": "entities_v1"})
    # Un prompt nuevo sí vuelve a leer la nota.
    conn.execute(_EXTRACTION, {**params, "version": "entities_v2"})

    with pytest.raises(IntegrityError, match="entity_extractions_article_id_prompt_version_key"):
        conn.execute(_EXTRACTION, {**params, "version": "entities_v1"})


def test_borrar_la_nota_borra_su_extraccion(conn: Connection) -> None:
    article = new_article(conn)
    conn.execute(
        _EXTRACTION,
        {
            "article": article,
            "version": "entities_v1",
            "status": "ok",
            "source": TextSource.FULL_TEXT,
            "output": "{}",
        },
    )

    conn.execute(text("DELETE FROM articles WHERE id = :a"), {"a": article})

    left = conn.execute(
        text("SELECT count(*) FROM entity_extractions WHERE article_id = :a"), {"a": article}
    ).scalar_one()
    assert left == 0


def test_la_misma_mencion_no_se_guarda_dos_veces(conn: Connection) -> None:
    entity = new_entity(conn)
    mention = new_mention(conn, entity, "fue detenido en Polanco")
    article = conn.execute(
        text("SELECT article_id FROM entity_mentions WHERE id = :m"), {"m": mention}
    ).scalar_one()

    with pytest.raises(IntegrityError, match="entity_mentions_once"):
        conn.execute(
            text(
                "INSERT INTO entity_mentions (entity_id, article_id, mention_text, role, "
                "confidence, evidence_span, extracted_by, prompt_version) "
                "VALUES (:e, :a, 'Eduardo N', 'event', 0.9, 'fue detenido en Polanco', "
                "'gpt-6-luna', 'entities_v1')"
            ),
            {"e": entity, "a": article},
        )


def test_lo_pendiente_de_un_caso_tiene_su_indice(conn: Connection) -> None:
    rows = conn.execute(
        text(
            "SELECT indexname FROM pg_indexes WHERE tablename IN "
            "('case_articles', 'entity_extractions', 'entity_mentions')"
        )
    ).scalars()

    assert {
        "case_articles_entities_todo",
        "entity_extractions_article_id_prompt_version_key",
        "entity_mentions_once",
    } <= set(rows)
