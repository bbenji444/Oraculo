"""Vínculos de un caso contra la base de pruebas (Fase 9.5, decisiones D6 a D8).

Comprueba lo que calcula el SQL: «aparecen juntas» solo entre confirmadas que
comparten notas del caso, con su confianza; que lo revisado gana y lo
descartado no vuelve; y que las fusiones se reflejan sin refrescar nada.

Los nombres son inventados.
"""

from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.persistence.entities_repository import PostgresEntityRepository
from app.adapters.persistence.relationships_repository import PostgresRelationshipRepository
from app.application.audit import AuditEntry
from app.application.ports.relationships import (
    RelationshipKey,
    RelationshipView,
    RelationshipWrite,
    find,
)
from app.domain.investigation import InvestigationAction, Origin, RelationshipType, ReviewStatus
from tests.integration.test_entities_repository import (
    BENJI,
    clean,
    new_article,
    new_case,
    sync_engine,
)
from tests.integration.test_resolution_repository import seed

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# Fixtures del módulo de la 9.4 (pytest las encuentra por nombre en este módulo).
__all__ = ["clean", "sync_engine"]

APPEARS = RelationshipType.APPEARS_WITH


def mention(engine: Engine, entity: int, article: int, label: str, *, role: str = "event") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entity_mentions (entity_id, article_id, mention_text, role, "
                "confidence, evidence_span, extracted_by) VALUES (:e, :a, :t, :r, 0.9, "
                ":t, 'gpt-6-luna')"
            ),
            {"e": entity, "a": article, "t": label, "r": role},
        )


def write(
    key: RelationshipKey, status: ReviewStatus, *, origin: Origin = Origin.COOCCURRENCE
) -> RelationshipWrite:
    return RelationshipWrite(
        relationship_id=None,
        key=key,
        custom_label=None,
        origin=origin,
        confidence=0.5 if origin is Origin.COOCCURRENCE else 1.0,
        review_status=status,
        reviewer="benji",
        notes=None,
    )


def audit(action: InvestigationAction) -> AuditEntry:
    return AuditEntry(BENJI, action, {"prueba": True})


def pairs(views: list[RelationshipView]) -> dict[tuple[int, int, str], tuple[str, float, int]]:
    return {
        (v.entity_a.entity_id, v.entity_b.entity_id, v.type.value): (
            v.review_status.value,
            v.confidence,
            len(v.shared_articles),
        )
        for v in views
    }


async def test_aparecen_juntas_solo_entre_confirmadas_y_crece_con_las_notas(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresRelationshipRepository(test_engine)
    case_id: UUID = new_case(sync_engine)
    one, two, three = (new_article(sync_engine, case_id) for _ in range(3))
    julian = seed(sync_engine, case_id, one, "Julián Ortega Ruiz", review="confirmed")
    ramon = seed(sync_engine, case_id, one, "Ramón Salas", review="confirmed")
    polanco = seed(sync_engine, case_id, three, "Polanco", kind="place", review="confirmed")
    seed(sync_engine, case_id, one, "Pedro Páramo")  # sugerida: no se vincula
    for article in (two, three):
        mention(sync_engine, julian, article, "Julián Ortega Ruiz")
        mention(sync_engine, ramon, article, "Ramón Salas")

    found = pairs(await repo.list_case(case_id))

    assert found == {
        (julian, ramon, "appears_with"): ("suggested", 0.9, 3),
        (julian, polanco, "appears_with"): ("suggested", 0.5, 1),
        (ramon, polanco, "appears_with"): ("suggested", 0.5, 1),
    }

    # Si una nota sale del caso, su evidencia también.
    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM case_articles WHERE article_id = :a"), {"a": three})
    assert pairs(await repo.list_case(case_id)) == {
        (julian, ramon, "appears_with"): ("suggested", 0.7, 2),
    }


async def test_lo_revisado_gana_y_lo_descartado_no_vuelve(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresRelationshipRepository(test_engine)
    case_id = new_case(sync_engine)
    article = new_article(sync_engine, case_id)
    julian = seed(sync_engine, case_id, article, "Julián Ortega Ruiz", review="confirmed")
    ramon = seed(sync_engine, case_id, article, "Ramón Salas", review="confirmed")
    salon = seed(sync_engine, case_id, article, "Salón Ramy", kind="org", review="confirmed")
    confirmed_key = RelationshipKey(julian, ramon, APPEARS)
    discarded_key = RelationshipKey(julian, salon, APPEARS)

    await repo.save(
        case_id,
        write(confirmed_key, ReviewStatus.CONFIRMED),
        audit(InvestigationAction.RELATIONSHIP_CONFIRMED),
    )
    await repo.save(
        case_id,
        write(discarded_key, ReviewStatus.DISCARDED),
        audit(InvestigationAction.RELATIONSHIP_DISCARDED),
    )
    # Un vínculo dirigido dibujado a mano.
    owns = RelationshipKey(julian, salon, RelationshipType.OWNS)
    await repo.save(
        case_id,
        write(owns, ReviewStatus.CONFIRMED, origin=Origin.HUMAN),
        audit(InvestigationAction.RELATIONSHIP_CREATED),
    )

    views = await repo.list_case(case_id)
    assert pairs(views) == {
        (julian, ramon, "appears_with"): ("confirmed", 0.5, 1),
        (julian, salon, "appears_with"): ("discarded", 0.5, 1),
        (julian, salon, "owns"): ("confirmed", 1.0, 1),
        (ramon, salon, "appears_with"): ("suggested", 0.5, 1),
    }
    confirmed = find(views, confirmed_key)
    assert confirmed is not None
    assert (confirmed.relationship_id is not None, confirmed.reviewed_by) == (True, "benji")
    with sync_engine.connect() as conn:
        actions = (
            conn.execute(
                text("SELECT action FROM audit_log WHERE entity_id = :c ORDER BY id"),
                {"c": str(case_id)},
            )
            .scalars()
            .all()
        )
    assert actions == ["relationship.confirmed", "relationship.discarded", "relationship.created"]


async def test_las_fusiones_se_reflejan_sin_refrescar(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresRelationshipRepository(test_engine)
    entities = PostgresEntityRepository(test_engine)
    case_id = new_case(sync_engine)
    one, two = new_article(sync_engine, case_id), new_article(sync_engine, case_id)
    julian = seed(sync_engine, case_id, one, "Julián Ortega Ruiz", review="confirmed")
    ramon = seed(sync_engine, case_id, two, "Ramón Salas", review="confirmed")
    # La sugerencia "Julián N" sale en la nota de Ramón.
    alias = seed(sync_engine, case_id, two, "Julián N")
    merged = audit(InvestigationAction.ENTITY_MERGED)
    assert await repo.list_case(case_id) == []

    await entities.merge(case_id, julian, alias, merged)

    # Al unirla, Julián ya comparte una nota con Ramón.
    assert pairs(await repo.list_case(case_id)) == {
        (julian, ramon, "appears_with"): ("suggested", 0.5, 1),
    }
    # Un vínculo guardado con una entidad que después se une se ve en la que quedó,
    # y uno entre dos del mismo grupo no se muestra.
    await entities.unmerge(case_id, alias, audit(InvestigationAction.ENTITY_UNMERGED))
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE entities SET review_status = 'confirmed', reviewed_by = 'benji', "
                "reviewed_at = now() WHERE id = :e"
            ),
            {"e": alias},
        )
    family = RelationshipKey(min(alias, ramon), max(alias, ramon), RelationshipType.FAMILY)
    await repo.save(
        case_id,
        write(family, ReviewStatus.CONFIRMED, origin=Origin.HUMAN),
        audit(InvestigationAction.RELATIONSHIP_CREATED),
    )
    same = RelationshipKey(julian, alias, RelationshipType.ASSOCIATE)
    await repo.save(
        case_id,
        write(same, ReviewStatus.CONFIRMED, origin=Origin.HUMAN),
        audit(InvestigationAction.RELATIONSHIP_CREATED),
    )
    await entities.merge(case_id, julian, alias, merged)

    found = pairs(await repo.list_case(case_id))
    assert found == {
        (julian, ramon, "appears_with"): ("suggested", 0.5, 1),
        (julian, ramon, "family"): ("confirmed", 1.0, 1),
    }


async def test_guardar_varios_es_una_transaccion(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresRelationshipRepository(test_engine)
    case_id = new_case(sync_engine)
    article = new_article(sync_engine, case_id)
    julian = seed(sync_engine, case_id, article, "Julián Ortega Ruiz", review="confirmed")
    ramon = seed(sync_engine, case_id, article, "Ramón Salas", review="confirmed")
    salon = seed(sync_engine, case_id, article, "Salón Ramy", kind="org", review="confirmed")
    confirmed = audit(InvestigationAction.RELATIONSHIP_CONFIRMED)
    good = write(RelationshipKey(julian, ramon, APPEARS), ReviewStatus.CONFIRMED)
    # Una entidad que no existe rompe la llave foránea: no se guarda ninguno.
    broken = write(RelationshipKey(julian, 999_999, APPEARS), ReviewStatus.CONFIRMED)

    with pytest.raises(IntegrityError):
        await repo.save_many(case_id, [(good, confirmed), (broken, confirmed)])
    untouched = pairs(await repo.list_case(case_id))
    await repo.save_many(
        case_id,
        [
            (good, confirmed),
            (write(RelationshipKey(julian, salon, APPEARS), ReviewStatus.CONFIRMED), confirmed),
        ],
    )

    assert {status for status, _, _ in untouched.values()} == {"suggested"}
    after = pairs(await repo.list_case(case_id))
    assert after[(julian, ramon, "appears_with")][0] == "confirmed"
    assert after[(julian, salon, "appears_with")][0] == "confirmed"
    assert after[(ramon, salon, "appears_with")][0] == "suggested"
    with sync_engine.connect() as conn:
        logged = conn.execute(
            text(
                "SELECT count(*) FROM audit_log WHERE entity_id = :c "
                "AND action = 'relationship.confirmed'"
            ),
            {"c": str(case_id)},
        ).scalar_one()
    assert logged == 2


async def test_cada_nota_dice_si_las_dos_participan_en_el_hecho(
    sync_engine: Engine, test_engine: AsyncEngine
) -> None:
    repo = PostgresRelationshipRepository(test_engine)
    case_id = new_case(sync_engine)
    one, two = new_article(sync_engine, case_id), new_article(sync_engine, case_id)
    # En la nota uno Julián y Ramón participan en el hecho; la fiscalía solo
    # se nombra. En la nota dos Julián solo se nombra junto a Ramón.
    julian = seed(sync_engine, case_id, one, "Julián Ortega Ruiz", review="confirmed")
    ramon = seed(sync_engine, case_id, one, "Ramón Salas", review="confirmed")
    fiscalia = seed(sync_engine, case_id, two, "Fiscalía", kind="org", review="confirmed")
    mention(sync_engine, fiscalia, one, "la Fiscalía", role="mentioned")
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE entity_mentions SET role = 'mentioned' WHERE entity_id = :e"),
            {"e": fiscalia},
        )
    mention(sync_engine, julian, two, "Julián", role="mentioned")
    mention(sync_engine, ramon, two, "Ramón Salas")

    views = {(v.entity_a.entity_id, v.entity_b.entity_id): v for v in await repo.list_case(case_id)}

    pair = views[(julian, ramon)]
    assert {(a.article_id, a.same_event) for a in pair.shared_articles} == {
        (one, True),
        (two, False),
    }
    assert (pair.same_event_count, pair.strength.value) == (1, "strong")
    weak = views[(julian, fiscalia)]
    assert (weak.same_event_count, weak.strength.value) == (0, "weak")
