"""Reglas del tablero de investigación que garantiza la base (Fase 9.2).

Cada valor de los enums de ``app.domain.investigation`` debe pasar el CHECK de
su columna, y lo prohibido (estatus "culpable", vincular una entidad consigo
misma, evidencia que es casi un artículo…) debe rechazarse aunque una fase
posterior se equivoque (ADR-0101, 0104 y 0105).
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.domain.geocoding import MentionRole
from app.domain.investigation import (
    EVIDENCE_SPAN_MAX_CHARS,
    EntityType,
    LegalStatus,
    Origin,
    RelationshipType,
    ReviewStatus,
)
from tests.integration.test_pipeline_tables import new_article, region_id

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


_ENTITY = text(
    "INSERT INTO entities (type, canonical_label, label_norm, legal_status, region_id, "
    "review_status, reviewed_by, reviewed_at) "
    "VALUES (:type, :label, upper(:label), :legal, :region, :review, :by, :at) RETURNING id"
)


def new_entity(
    conn: Connection,
    kind: str = EntityType.PERSON,
    label: str = "Eduardo N",
    legal_status: str | None = None,
    *,
    region: int | None = None,
    review: str = ReviewStatus.SUGGESTED,
    reviewed_by: str | None = None,
    reviewed_at: str | None = None,
) -> int:
    params = {
        "type": kind,
        "label": label,
        "legal": legal_status,
        "region": region,
        "review": review,
        "by": reviewed_by,
        "at": reviewed_at,
    }
    return int(conn.execute(_ENTITY, params).scalar_one())


def new_mention(conn: Connection, entity: int, evidence: str = "fue detenido") -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO entity_mentions (entity_id, article_id, mention_text, role, "
                "confidence, evidence_span, extracted_by, prompt_version) "
                "VALUES (:entity, :article, 'Eduardo N', 'event', 0.9, :evidence, "
                "'gpt-6-luna', 'enrich_v3') RETURNING id"
            ),
            {
                "entity": entity,
                "article": new_article(conn, f"https://medio.mx/{uuid4()}"),
                "evidence": evidence,
            },
        ).scalar_one()
    )


_RELATIONSHIP = text(
    "INSERT INTO relationships (entity_a, entity_b, type, custom_label, origin, confidence) "
    "VALUES (:a, :b, :type, :label, 'cooccurrence', 0.6) RETURNING id"
)


def new_relationship(
    conn: Connection,
    a: int,
    b: int,
    kind: str = RelationshipType.SAME_EVENT,
    custom_label: str | None = None,
) -> int:
    params = {"a": a, "b": b, "type": kind, "label": custom_label}
    return int(conn.execute(_RELATIONSHIP, params).scalar_one())


# --- Entidades --------------------------------------------------------------------


def test_cada_tipo_y_estatus_legal_del_dominio_pasa_su_check(conn: Connection) -> None:
    for kind in EntityType:
        new_entity(conn, kind, f"Entidad {kind.value}")
    for status in LegalStatus:
        new_entity(conn, EntityType.PERSON, f"Persona {status.value}", status)


def test_una_entidad_nace_sugerida(conn: Connection) -> None:
    entity = new_entity(conn)

    status = conn.execute(
        text("SELECT review_status FROM entities WHERE id = :id"), {"id": entity}
    ).scalar_one()

    assert status == ReviewStatus.SUGGESTED


@pytest.mark.parametrize("forbidden", ["culpable", "guilty", "convicted"])
def test_culpable_no_existe(conn: Connection, forbidden: str) -> None:
    with pytest.raises(IntegrityError, match="entities_legal_status_known"):
        new_entity(conn, EntityType.PERSON, "Eduardo N", forbidden)


def test_el_estatus_legal_es_solo_de_personas(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="entities_legal_status_only_people"):
        new_entity(conn, EntityType.ORG, "FGR", LegalStatus.ALLEGED)


def test_solo_los_lugares_se_ligan_al_catalogo(conn: Connection) -> None:
    new_entity(conn, EntityType.PLACE, "Polanco", region=region_id(conn))

    with pytest.raises(IntegrityError, match="entities_catalog_only_places"):
        new_entity(conn, EntityType.PERSON, "Eduardo N", region=region_id(conn))


def test_confirmar_o_descartar_dice_quien_y_cuando(conn: Connection) -> None:
    new_entity(conn, review="confirmed", reviewed_by="benji", reviewed_at="2026-10-20T20:00Z")

    with pytest.raises(IntegrityError, match="entities_review_signed"):
        new_entity(conn, review="discarded")


def test_una_entidad_no_se_fusiona_consigo_misma(conn: Connection) -> None:
    entity = new_entity(conn)

    with pytest.raises(IntegrityError, match="entities_not_merged_into_itself"):
        conn.execute(text("UPDATE entities SET merged_into = id WHERE id = :id"), {"id": entity})


def test_un_alias_por_entidad_sin_repetir(conn: Connection) -> None:
    entity = new_entity(conn)
    insert = text(
        "INSERT INTO entity_aliases (entity_id, alias, alias_norm) "
        "VALUES (:entity, 'Eduardo Ederly', 'EDUARDO EDERLY')"
    )
    conn.execute(insert, {"entity": entity})

    with pytest.raises(IntegrityError, match="entity_aliases_entity_id_alias_norm_key"):
        conn.execute(insert, {"entity": entity})


# --- Menciones ----------------------------------------------------------------------


def test_cada_rol_de_mencion_pasa_su_check(conn: Connection) -> None:
    entity = new_entity(conn)
    for role in MentionRole:
        conn.execute(
            text(
                "INSERT INTO entity_mentions (entity_id, article_id, mention_text, role, "
                "confidence, evidence_span, extracted_by) "
                "VALUES (:entity, :article, 'Eduardo N', :role, 0.5, 'cita', 'gpt-6-luna')"
            ),
            {"entity": entity, "article": new_article(conn, f"https://m.mx/{role}"), "role": role},
        )


def test_la_evidencia_es_una_cita_corta_y_no_vacia(conn: Connection) -> None:
    entity = new_entity(conn)
    new_mention(conn, entity, "x" * EVIDENCE_SPAN_MAX_CHARS)

    for bad in ("", "   ", "x" * (EVIDENCE_SPAN_MAX_CHARS + 1)):
        with pytest.raises(IntegrityError, match="evidence_span_short"), conn.begin_nested():
            new_mention(conn, entity, bad)


def test_la_pista_de_estatus_legal_tampoco_admite_culpable(conn: Connection) -> None:
    entity = new_entity(conn)

    with pytest.raises(IntegrityError, match="entity_mentions_legal_status_hint_known"):
        conn.execute(
            text(
                "INSERT INTO entity_mentions (entity_id, article_id, mention_text, role, "
                "legal_status_hint, confidence, evidence_span, extracted_by) "
                "VALUES (:entity, :article, 'Eduardo N', 'event', 'culpable', 0.9, 'cita', 'x')"
            ),
            {"entity": entity, "article": new_article(conn)},
        )


def test_borrar_la_nota_borra_sus_menciones(conn: Connection) -> None:
    entity = new_entity(conn)
    mention = new_mention(conn, entity)

    conn.execute(
        text(
            "DELETE FROM articles WHERE id = "
            "(SELECT article_id FROM entity_mentions WHERE id = :id)"
        ),
        {"id": mention},
    )

    left = conn.execute(
        text("SELECT count(*) FROM entity_mentions WHERE id = :id"), {"id": mention}
    )
    assert left.scalar_one() == 0


# --- Vínculos -----------------------------------------------------------------------


def test_cada_tipo_y_origen_de_vinculo_pasa_su_check(conn: Connection) -> None:
    a, b = new_entity(conn, label="A"), new_entity(conn, label="B")
    for kind in RelationshipType:
        label = "socio de" if kind is RelationshipType.CUSTOM else None
        new_relationship(conn, a, b, kind, custom_label=label)
    for origin in Origin:
        conn.execute(
            text(
                "UPDATE relationships SET origin = :origin "
                "WHERE entity_a = :a AND type = 'same_event'"
            ),
            {"origin": origin, "a": a},
        )


def test_un_vinculo_no_une_una_entidad_consigo_misma(conn: Connection) -> None:
    a = new_entity(conn)

    with pytest.raises(IntegrityError, match="relationships_two_entities"):
        new_relationship(conn, a, a)


def test_el_mismo_vinculo_no_se_guarda_dos_veces(conn: Connection) -> None:
    a, b = new_entity(conn, label="A"), new_entity(conn, label="B")
    new_relationship(conn, a, b)

    with pytest.raises(IntegrityError, match="relationships_entity_a_entity_b_type_key"):
        new_relationship(conn, a, b)


def test_la_etiqueta_propia_va_solo_con_el_tipo_custom(conn: Connection) -> None:
    a, b = new_entity(conn, label="A"), new_entity(conn, label="B")

    with pytest.raises(IntegrityError, match="custom_label_only_custom"), conn.begin_nested():
        new_relationship(conn, a, b, RelationshipType.CUSTOM)
    with pytest.raises(IntegrityError, match="custom_label_only_custom"):
        new_relationship(conn, a, b, RelationshipType.FAMILY, custom_label="primo")


def test_un_vinculo_nace_sugerido_y_al_revisarlo_dice_quien(conn: Connection) -> None:
    a, b = new_entity(conn, label="A"), new_entity(conn, label="B")
    link = new_relationship(conn, a, b)

    status = conn.execute(
        text("SELECT review_status FROM relationships WHERE id = :id"), {"id": link}
    ).scalar_one()
    assert status == ReviewStatus.SUGGESTED
    with pytest.raises(IntegrityError, match="relationships_review_signed"):
        conn.execute(
            text("UPDATE relationships SET review_status = 'confirmed' WHERE id = :id"),
            {"id": link},
        )


# --- external_links (reservada) -----------------------------------------------------


def test_external_links_existe_vacia_y_documentada(conn: Connection) -> None:
    count = conn.execute(text("SELECT count(*) FROM external_links")).scalar_one()
    comment = conn.execute(
        text("SELECT obj_description('external_links'::regclass, 'pg_class')")
    ).scalar_one()

    assert count == 0
    assert "sin uso en la Fase 9" in comment


# --- Índices ------------------------------------------------------------------------


def test_cada_columna_de_filtro_tiene_su_indice(conn: Connection) -> None:
    rows = conn.execute(
        text(
            "SELECT indexname FROM pg_indexes WHERE tablename IN "
            "('entities', 'entity_aliases', 'entity_mentions', 'relationships', "
            "'external_links')"
        )
    ).scalars()

    assert {
        "entities_label_trgm",
        "entities_type_review_id",
        "entities_merged_into",
        "entities_region",
        "entities_place",
        "entity_aliases_alias_trgm",
        "entity_mentions_entity",
        "entity_mentions_article_entity",
        "relationships_entity_b",
        "relationships_review_id",
        "external_links_entity",
    } <= set(rows)
