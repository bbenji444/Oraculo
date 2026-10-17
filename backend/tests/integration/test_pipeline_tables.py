"""Reglas de las tablas de búsquedas, notas y ubicaciones que garantiza la base (§6)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings

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


def region_id(conn: Connection) -> int:
    # Cualquier región sirve; si el catálogo de pruebas está vacío, se crea una.
    found = conn.execute(text("SELECT id FROM regions LIMIT 1")).scalar()
    if found is not None:
        return int(found)
    return int(
        conn.execute(
            text(
                "INSERT INTO regions (level, code, country_code, name, name_norm, centroid) "
                "VALUES ('country', 'ZZZ', 'ZZZ', 'Prueba', 'PRUEBA', "
                "ST_SetSRID(ST_MakePoint(0, 0), 4326)) RETURNING id"
            )
        ).scalar_one()
    )


def new_search(conn: Connection, status: str = "pending") -> str:
    return str(
        conn.execute(
            text(
                "INSERT INTO searches (user_id, region_id, date_from, date_to, status) "
                "VALUES ('prueba', :region, '2026-10-10', '2026-10-16', :status) RETURNING id"
            ),
            {"region": region_id(conn), "status": status},
        ).scalar_one()
    )


def new_article(conn: Connection, url: str = "https://medio.mx/a") -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO articles (url_canonical, url_hash, title, title_norm) "
                "VALUES (:url, md5(:url), 'Nota', 'NOTA') RETURNING id"
            ),
            {"url": url},
        ).scalar_one()
    )


def test_una_busqueda_nace_pendiente_y_con_estado_conocido(conn: Connection) -> None:
    search = new_search(conn)

    status = conn.execute(text("SELECT status FROM searches WHERE id = :id"), {"id": search})
    assert status.scalar_one() == "pending"
    with pytest.raises(IntegrityError, match="searches_status_known"):
        new_search(conn, "quizas")


def test_fechas_al_reves_se_rechazan(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="searches_dates_in_order"):
        conn.execute(
            text(
                "INSERT INTO searches (user_id, region_id, date_from, date_to) "
                "VALUES ('prueba', :region, '2026-10-16', '2026-10-10')"
            ),
            {"region": region_id(conn)},
        )


def test_una_nota_se_guarda_una_vez_por_url(conn: Connection) -> None:
    new_article(conn)

    with pytest.raises(IntegrityError, match="articles_url_hash_key"):
        new_article(conn)


def test_una_sola_ubicacion_principal_por_nota(conn: Connection) -> None:
    article = new_article(conn)
    insert = text(
        "INSERT INTO article_locations (article_id, mention_text, role, precision, confidence, "
        "is_primary) VALUES (:a, 'Iztapalapa', 'event', 'municipality', 0.9, true)"
    )
    conn.execute(insert, {"a": article})

    with pytest.raises(IntegrityError, match="article_locations_one_primary"):
        conn.execute(insert, {"a": article})


@pytest.mark.parametrize(
    ("role", "precision", "confidence", "constraint"),
    [
        ("inventado", "state", 0.5, "article_locations_role_known"),
        ("event", "colonia", 0.5, "article_locations_precision_known"),
        ("event", "state", 1.5, "article_locations_confidence_range"),
    ],
)
def test_ubicaciones_con_valores_validos(
    conn: Connection, role: str, precision: str, confidence: float, constraint: str
) -> None:
    article = new_article(conn)

    with pytest.raises(IntegrityError, match=constraint):
        conn.execute(
            text(
                "INSERT INTO article_locations (article_id, mention_text, role, precision, "
                "confidence) VALUES (:a, 'x', :role, :precision, :confidence)"
            ),
            {"a": article, "role": role, "precision": precision, "confidence": confidence},
        )


def test_las_consultas_de_un_proveedor_apuntan_a_una_busqueda_real(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="provider_queries_search_fk"):
        conn.execute(
            text(
                "INSERT INTO provider_queries (search_id, provider, query_text, status) "
                "VALUES (gen_random_uuid(), 'searchapi', 'x', 'ok')"
            )
        )


def test_existen_los_indices(conn: Connection) -> None:
    names = set(conn.execute(text("SELECT indexname FROM pg_indexes")).scalars())

    assert {
        "searches_created_id",
        "searches_user_created",
        "searches_region",
        "search_concepts_concept",
        "articles_url_hash_key",
        "articles_published_id",
        "articles_title_trgm",
        "articles_text_hash",
        "article_texts_extracted",
        "article_concepts_concept",
        "article_locations_article",
        "article_locations_region",
        "article_locations_point",
        "article_locations_one_primary",
        "search_results_article",
        "processing_errors_search",
        "processing_errors_article",
        "processing_errors_created_id",
    } <= names
