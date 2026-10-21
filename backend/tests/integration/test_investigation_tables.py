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
    CaseEntityStatus,
    CaseMemberRole,
    CaseStatus,
    EntityType,
    LegalStatus,
    Origin,
    RelationshipType,
    ReviewStatus,
    Sensitivity,
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


# --- Casos (migración 0019) ---------------------------------------------------------


def new_case(conn: Connection, status: str = "open", closed_at: str | None = None) -> str:
    return str(
        conn.execute(
            text(
                "INSERT INTO cases (name, name_norm, status, created_by, closed_at) "
                "VALUES ('Homicidio estilista Polanco', 'HOMICIDIO ESTILISTA POLANCO', "
                ":status, 'benji', :closed) RETURNING id"
            ),
            {"status": status, "closed": closed_at},
        ).scalar_one()
    )


def add_member(conn: Connection, case: str, user: str, role: str) -> None:
    conn.execute(
        text(
            "INSERT INTO case_members (case_id, user_id, role, added_by) "
            "VALUES (:case, :user, :role, 'benji')"
        ),
        {"case": case, "user": user, "role": role},
    )


def add_note(
    conn: Connection,
    case: str,
    *,
    entity: int | None = None,
    article: int | None = None,
    relationship: int | None = None,
) -> int:
    params = {"case": case, "entity": entity, "article": article, "relationship": relationship}
    return int(
        conn.execute(
            text(
                "INSERT INTO case_notes (case_id, body, entity_id, article_id, relationship_id, "
                "author) VALUES (:case, 'verificar relación con caso previo', :entity, "
                ":article, :relationship, 'benji') RETURNING id"
            ),
            params,
        ).scalar_one()
    )


def test_un_caso_nace_abierto_y_con_sensibilidad_normal(conn: Connection) -> None:
    case = new_case(conn)

    row = conn.execute(
        text("SELECT status, sensitivity FROM cases WHERE id = :id"), {"id": case}
    ).one()

    assert (row.status, row.sensitivity) == (CaseStatus.OPEN, Sensitivity.NORMAL)


def test_cada_estado_y_sensibilidad_del_dominio_pasa_su_check(conn: Connection) -> None:
    for status in CaseStatus:
        closed = None if status is CaseStatus.OPEN else "2026-10-21T10:00Z"
        case = new_case(conn, status, closed)
        for sensitivity in Sensitivity:
            conn.execute(
                text("UPDATE cases SET sensitivity = :s WHERE id = :id"),
                {"s": sensitivity, "id": case},
            )


def test_la_fecha_de_cierre_va_con_el_estado(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="cases_closed_at_matches_status"), conn.begin_nested():
        new_case(conn, "open", "2026-10-21T10:00Z")
    with pytest.raises(IntegrityError, match="cases_closed_at_matches_status"):
        new_case(conn, "closed")


def test_roles_de_miembro_y_un_solo_dueno_por_caso(conn: Connection) -> None:
    case = new_case(conn)
    for number, role in enumerate(CaseMemberRole):
        add_member(conn, case, f"analista-{number}", role)

    with pytest.raises(IntegrityError, match="case_members_one_owner"), conn.begin_nested():
        add_member(conn, case, "otra-persona", CaseMemberRole.OWNER)
    with pytest.raises(IntegrityError, match="case_members_pkey"):
        add_member(conn, case, "analista-1", CaseMemberRole.VIEWER)


def test_una_nota_y_una_entidad_entran_una_vez_por_caso(conn: Connection) -> None:
    case, article, entity = new_case(conn), new_article(conn), new_entity(conn)
    add_article = text(
        "INSERT INTO case_articles (case_id, article_id, added_by) VALUES (:c, :a, 'benji')"
    )
    add_entity = text(
        "INSERT INTO case_entities (case_id, entity_id, case_status, added_by) "
        "VALUES (:c, :e, :s, 'benji')"
    )
    conn.execute(add_article, {"c": case, "a": article})
    conn.execute(add_entity, {"c": case, "e": entity, "s": CaseEntityStatus.ACTIVE})

    with pytest.raises(IntegrityError, match="case_articles_pkey"), conn.begin_nested():
        conn.execute(add_article, {"c": case, "a": article})
    with pytest.raises(IntegrityError, match="case_entities_pkey"):
        conn.execute(add_entity, {"c": case, "e": entity, "s": CaseEntityStatus.ACTIVE})


def test_cada_estado_de_entidad_en_el_caso_pasa_su_check(conn: Connection) -> None:
    case = new_case(conn)
    for status in CaseEntityStatus:
        conn.execute(
            text(
                "INSERT INTO case_entities (case_id, entity_id, case_status, added_by) "
                "VALUES (:c, :e, :s, 'benji')"
            ),
            {"c": case, "e": new_entity(conn, label=f"Entidad {status}"), "s": status},
        )


def test_una_nota_del_investigador_se_ancla_a_lo_mas_a_una_cosa(conn: Connection) -> None:
    case, entity = new_case(conn), new_entity(conn)
    add_note(conn, case)
    add_note(conn, case, entity=entity)

    with pytest.raises(IntegrityError, match="case_notes_one_anchor"):
        add_note(conn, case, entity=entity, article=new_article(conn))


def test_si_se_borra_el_ancla_la_nota_se_queda_sin_ancla(conn: Connection) -> None:
    case, entity = new_case(conn), new_entity(conn)
    note = add_note(conn, case, entity=entity)

    conn.execute(text("DELETE FROM entities WHERE id = :id"), {"id": entity})

    anchor = conn.execute(
        text("SELECT entity_id FROM case_notes WHERE id = :id"), {"id": note}
    ).scalar_one()
    assert anchor is None


def test_borrar_un_caso_no_borra_las_notas_ni_las_entidades(conn: Connection) -> None:
    case, article, entity = new_case(conn), new_article(conn), new_entity(conn)
    add_member(conn, case, "benji", CaseMemberRole.OWNER)
    conn.execute(
        text("INSERT INTO case_articles (case_id, article_id, added_by) VALUES (:c, :a, 'b')"),
        {"c": case, "a": article},
    )
    conn.execute(
        text("INSERT INTO case_entities (case_id, entity_id, added_by) VALUES (:c, :e, 'b')"),
        {"c": case, "e": entity},
    )
    add_note(conn, case, entity=entity)

    conn.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case})

    left = conn.execute(
        text(
            "SELECT (SELECT count(*) FROM case_members WHERE case_id = :c) "
            "+ (SELECT count(*) FROM case_articles WHERE case_id = :c) "
            "+ (SELECT count(*) FROM case_entities WHERE case_id = :c) "
            "+ (SELECT count(*) FROM case_notes WHERE case_id = :c)"
        ),
        {"c": case},
    ).scalar_one()
    kept = conn.execute(
        text(
            "SELECT (SELECT count(*) FROM articles WHERE id = :a) "
            "+ (SELECT count(*) FROM entities WHERE id = :e)"
        ),
        {"a": article, "e": entity},
    ).scalar_one()
    assert (left, kept) == (0, 2)


def test_los_casos_y_la_bitacora_tienen_sus_indices(conn: Connection) -> None:
    rows = conn.execute(
        text(
            "SELECT indexname FROM pg_indexes WHERE tablename IN "
            "('cases', 'case_members', 'case_articles', 'case_entities', 'case_notes', "
            "'audit_log')"
        )
    ).scalars()

    assert {
        "cases_status_updated_id",
        "cases_created_by",
        "case_members_user_case",
        "case_members_one_owner",
        "case_articles_article",
        "case_entities_entity",
        "case_notes_case_created_id",
        "case_notes_entity",
        "case_notes_article",
        "case_notes_relationship",
        "audit_log_user_created",
    } <= set(rows)
