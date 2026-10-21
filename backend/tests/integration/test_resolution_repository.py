"""Sugerir, unir y separar entidades contra la base de pruebas (Fase 9.5, D2 a D5).

Comprueba lo que solo la base puede garantizar: qué pares sugiere el SQL
(nombre igual, alias en común, trigramas), que un «No son la misma» no
vuelve, que unir no mueve filas y se puede deshacer exacto, y que volver a
agregar una nota no duplica evidencia aunque su entidad ya esté unida.

Los nombres son inventados.
"""

from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.entities_repository import PostgresEntityRepository
from app.application.audit import AuditEntry
from app.domain.entity_resolution import MergeReason, entity_name_norm
from app.domain.errors import EntityMergeError
from app.domain.investigation import InvestigationAction, LegalStatus, ReviewStatus
from tests.integration.test_entities_repository import (
    BENJI,
    PLAIN,
    PLAIN_BODY,
    QUOTED,
    QUOTED_BODY,
    add_to_case,
    audit,
    clean,
    extraction,
    new_article,
    new_case,
    sync_engine,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# Fixtures del módulo de la 9.4 (pytest las encuentra por nombre en este módulo).
__all__ = ["clean", "sync_engine"]


def seed(
    engine: Engine,
    case_id: UUID,
    article: int,
    label: str,
    *,
    kind: str = "person",
    aliases: tuple[str, ...] = (),
    review: str = "suggested",
) -> int:
    """Una entidad del caso con una mención en ``article`` (como la dejaría la 9.4)."""
    signed = review != "suggested"
    with engine.begin() as conn:
        entity = int(
            conn.execute(
                text(
                    "INSERT INTO entities (type, canonical_label, label_norm, review_status, "
                    "legal_status, reviewed_by, reviewed_at) VALUES (:type, :label, :norm, "
                    ":review, :legal, :by, CASE WHEN :signed THEN now() END) RETURNING id"
                ),
                {
                    "type": kind,
                    "label": label,
                    "norm": entity_name_norm(label),
                    "review": review,
                    "legal": "alleged"
                    if signed and kind == "person" and review == "confirmed"
                    else None,
                    "by": "benji" if signed else None,
                    "signed": signed,
                },
            ).scalar_one()
        )
        conn.execute(
            text("INSERT INTO case_entities (case_id, entity_id, added_by) VALUES (:c, :e, 'b')"),
            {"c": case_id, "e": entity},
        )
        for alias in aliases:
            conn.execute(
                text(
                    "INSERT INTO entity_aliases (entity_id, alias, alias_norm) VALUES (:e, :a, :n)"
                ),
                {"e": entity, "a": alias, "n": entity_name_norm(alias)},
            )
        conn.execute(
            text(
                "INSERT INTO entity_mentions (entity_id, article_id, mention_text, role, "
                "confidence, evidence_span, extracted_by) VALUES (:e, :a, :t, 'event', 0.9, "
                ":t, 'gpt-6-luna')"
            ),
            {"e": entity, "a": article, "t": label},
        )
    return entity


async def suggestions(
    repo: PostgresEntityRepository, case_id: UUID
) -> dict[tuple[int, int], frozenset[MergeReason]]:
    found = await repo.merge_suggestions(case_id)
    return {(s.first.entity_id, s.second.entity_id): s.reasons for s in found}


def merge_audit(action: InvestigationAction = InvestigationAction.ENTITY_MERGED) -> AuditEntry:
    return AuditEntry(BENJI, action, {"prueba": True})


async def test_sugiere_mismo_nombre_alias_en_comun_y_nombre_parecido(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    article = new_article(sync_engine, case_id)
    quoted = seed(sync_engine, case_id, article, "Julián “N”")
    plain = seed(sync_engine, case_id, article, "Julián N")
    ramon = seed(sync_engine, case_id, article, "Ramón Salas", aliases=("Ramy Style",))
    ramy = seed(sync_engine, case_id, article, "Ramy Style")
    fiscalia = seed(
        sync_engine,
        case_id,
        article,
        "Fiscalía General de Justicia de la Ciudad de México",
        kind="org",
    )
    fiscalia_corta = seed(
        sync_engine,
        case_id,
        article,
        "Fiscalía General de Justicia de Ciudad de México",
        kind="org",
    )
    # Mismo nombre que una persona pero otro tipo: nunca se sugiere con ella.
    seed(sync_engine, case_id, article, "Ramy Style", kind="org")
    # Lo descartado no se sugiere.
    seed(sync_engine, case_id, article, "Pedro Páramo", review="discarded")
    seed(sync_engine, case_id, article, "Pedro Páramo")

    found = await suggestions(repo, case_id)

    assert found == {
        (quoted, plain): frozenset(
            {MergeReason.SAME_NAME, MergeReason.SHARED_NAME, MergeReason.SIMILAR_NAME}
        ),
        (ramon, ramy): frozenset({MergeReason.SHARED_NAME}),
        (fiscalia, fiscalia_corta): frozenset({MergeReason.SIMILAR_NAME}),
    }
    # Sugerir no fusiona nada.
    with sync_engine.connect() as conn:
        merged = conn.execute(text("SELECT count(*) FROM entities WHERE merged_into IS NOT NULL"))
        assert merged.scalar_one() == 0


async def test_no_son_la_misma_no_vuelve_a_salir(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    article = new_article(sync_engine, case_id)
    first = seed(sync_engine, case_id, article, "Julián “N”")
    second = seed(sync_engine, case_id, article, "Julián N")
    dismiss = merge_audit(InvestigationAction.ENTITY_MERGE_DISMISSED)

    assert await repo.dismiss_merge(case_id, first, second, dismiss) is True
    assert await repo.dismiss_merge(case_id, first, second, dismiss) is False

    assert await suggestions(repo, case_id) == {}
    with sync_engine.connect() as conn:
        actions = conn.execute(
            text(
                "SELECT count(*) FROM audit_log WHERE action = 'entity.merge_dismissed' "
                "AND entity_id = :c"
            ),
            {"c": str(case_id)},
        ).scalar_one()
    assert actions == 1


async def test_unir_suma_la_evidencia_y_separar_la_devuelve_exacta(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    one, two = new_article(sync_engine, case_id), new_article(sync_engine, case_id)
    keep = seed(
        sync_engine, case_id, one, "Julián Ortega Ruiz", aliases=("Julián N",), review="confirmed"
    )
    merge = seed(sync_engine, case_id, two, "Julián N")
    assert set(await suggestions(repo, case_id)) == {(keep, merge)}

    kept = await repo.merge(case_id, keep, merge, merge_audit())

    assert kept.review_status is ReviewStatus.CONFIRMED
    assert kept.legal_status is LegalStatus.ALLEGED
    assert kept.article_count == 2
    assert [m.entity_id for m in kept.merged] == [merge]
    assert sorted({m.entity_id for m in kept.mentions}) == sorted([keep, merge])
    assert kept.own_mention_ids != tuple(m.mention_id for m in kept.mentions)
    assert [e.entity_id for e in await repo.list_entities(case_id, ReviewStatus.SUGGESTED)] == []
    counts = await repo.review_counts(case_id)
    assert (counts[ReviewStatus.CONFIRMED], counts[ReviewStatus.SUGGESTED]) == (1, 0)
    assert await suggestions(repo, case_id) == {}
    candidate = await repo.merge_candidate(case_id, merge)
    assert candidate is not None
    assert candidate.merged_into == keep
    with pytest.raises(EntityMergeError, match="cambió"):
        await repo.merge(case_id, keep, merge, merge_audit())

    separated = await repo.unmerge(case_id, merge, merge_audit(InvestigationAction.ENTITY_UNMERGED))

    assert separated.entity_id == merge
    assert [m.entity_id for m in separated.mentions] == [merge]
    restored = await repo.get_entity(case_id, keep)
    assert restored is not None
    assert (restored.article_count, restored.merged) == (1, ())
    assert set(await suggestions(repo, case_id)) == {(keep, merge)}
    with pytest.raises(EntityMergeError, match="no está unida"):
        await repo.unmerge(case_id, merge, merge_audit(InvestigationAction.ENTITY_UNMERGED))
    with sync_engine.connect() as conn:
        actions = (
            conn.execute(
                text("SELECT action FROM audit_log WHERE entity_id = :c ORDER BY id"),
                {"c": str(case_id)},
            )
            .scalars()
            .all()
        )
    assert actions == ["entity.merged", "entity.unmerged"]


async def test_una_union_en_cadena_se_ve_entera_y_se_separa_por_partes(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    article = new_article(sync_engine, case_id)
    top = seed(sync_engine, case_id, article, "Julián Ortega Ruiz")
    middle = seed(sync_engine, case_id, article, "Julián Ortega")
    bottom = seed(sync_engine, case_id, article, "Julián N")
    await repo.merge(case_id, middle, bottom, merge_audit())
    await repo.merge(case_id, top, middle, merge_audit())

    whole = await repo.get_entity(case_id, top)
    assert whole is not None
    assert {m.entity_id for m in whole.merged} == {middle, bottom}
    assert len(whole.mentions) == 3

    # Separar la del medio se lleva lo que se le había unido a ella.
    await repo.unmerge(case_id, middle, merge_audit(InvestigationAction.ENTITY_UNMERGED))

    middle_again = await repo.get_entity(case_id, middle)
    top_again = await repo.get_entity(case_id, top)
    assert middle_again is not None
    assert top_again is not None
    assert [m.entity_id for m in middle_again.merged] == [bottom]
    assert top_again.merged == ()


async def test_separar_menciones_crea_una_sugerencia_con_ellas(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    one, two = new_article(sync_engine, case_id), new_article(sync_engine, case_id)
    entity = seed(sync_engine, case_id, one, "Julián N")
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entity_mentions (entity_id, article_id, mention_text, role, "
                "confidence, evidence_span, extracted_by) VALUES (:e, :a, 'Julián N', "
                "'mentioned', 0.8, 'otro Julián N', 'gpt-6-luna')"
            ),
            {"e": entity, "a": two},
        )
    before = await repo.get_entity(case_id, entity)
    assert before is not None
    other = next(m.mention_id for m in before.mentions if m.article_id == two)

    created = await repo.split(
        case_id, entity, [other], merge_audit(InvestigationAction.ENTITY_SPLIT)
    )

    assert (created.label, created.review_status) == ("Julián N", ReviewStatus.SUGGESTED)
    assert [m.mention_id for m in created.mentions] == [other]
    after = await repo.get_entity(case_id, entity)
    assert after is not None
    assert [m.article_id for m in after.mentions] == [one]
    # Las dos siguen llamándose igual: se ofrecen para unir, por si fue un error.
    assert set(await suggestions(repo, case_id)) == {(entity, created.entity_id)}
    with pytest.raises(EntityMergeError, match="no son de esa entidad"):
        await repo.split(case_id, entity, [other], merge_audit(InvestigationAction.ENTITY_SPLIT))


async def test_volver_a_agregar_una_nota_no_duplica_aunque_su_entidad_se_haya_unido(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    quoted = new_article(sync_engine, case_id, body=QUOTED_BODY)
    plain = new_article(sync_engine, case_id, body=PLAIN_BODY)
    await repo.materialize(case_id, extraction(quoted, QUOTED, body=QUOTED_BODY), 0.0, audit())
    [first] = await repo.list_entities(case_id, ReviewStatus.SUGGESTED)
    await repo.review(
        case_id,
        first.entity_id,
        status=ReviewStatus.CONFIRMED,
        legal_status=LegalStatus.DETAINED,
        reviewer="benji",
        audit=merge_audit(InvestigationAction.ENTITY_CONFIRMED),
    )
    plain_extraction = extraction(plain, PLAIN, body=PLAIN_BODY)
    await repo.materialize(case_id, plain_extraction, 0.0, audit())
    [second] = await repo.list_entities(case_id, ReviewStatus.SUGGESTED)
    await repo.merge(case_id, first.entity_id, second.entity_id, merge_audit())

    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM case_articles WHERE article_id = :a"), {"a": plain})
        add_to_case(conn, case_id, plain)
    result = await repo.materialize(case_id, plain_extraction, 0.0, audit())

    assert result is not None
    assert result.skipped == 1
    assert await repo.list_entities(case_id, ReviewStatus.SUGGESTED) == []
    kept = await repo.get_entity(case_id, first.entity_id)
    assert kept is not None
    assert kept.article_count == 2
