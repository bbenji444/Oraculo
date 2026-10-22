"""Casos de uso de los vínculos de un caso con repositorios en memoria (Fase 9.5, D6 a D9)."""

from dataclasses import replace
from uuid import UUID

import pytest

from app.application.ports.relationships import RelationshipKey
from app.application.use_cases.cases import UpdateCase
from app.application.use_cases.relationships import (
    CreateRelationship,
    ListRelationships,
    RelationshipInput,
    ReviewRelationship,
)
from app.domain.case import CaseChanges
from app.domain.errors import (
    CaseClosedError,
    CaseForbiddenError,
    InvalidRequestError,
    RelationshipNotFoundError,
    RelationshipValidationError,
)
from app.domain.investigation import (
    CaseStatus,
    InvestigationAction,
    LegalStatus,
    Origin,
    RelationshipType,
    ReviewStatus,
)
from tests.unit.application.test_entities_use_cases import BENJI, LECTORA, new_case, person
from tests.unit.fake_cases import FakeCaseRepository
from tests.unit.fake_entities import FakeEntityRepository
from tests.unit.fake_relationships import FakeRelationshipRepository, suggested

pytestmark = pytest.mark.anyio

APPEARS = RelationshipType.APPEARS_WITH


async def setup() -> tuple[
    FakeCaseRepository, FakeEntityRepository, FakeRelationshipRepository, UUID
]:
    cases, entities, relationships = (
        FakeCaseRepository(),
        FakeEntityRepository(),
        FakeRelationshipRepository(),
    )
    case_id = await new_case(cases)
    for entity_id in (1, 2, 3):
        confirmed = replace(
            person(entity_id),
            review_status=ReviewStatus.CONFIRMED,
            legal_status=LegalStatus.ALLEGED,
        )
        entities.add_entity(case_id, confirmed)
    entities.add_entity(case_id, person(4))
    return cases, entities, relationships, case_id


async def test_lista_por_estado_con_los_de_mas_confianza_primero() -> None:
    cases, _, relationships, case_id = await setup()
    relationships.views[case_id] = [suggested(1, 2), suggested(1, 3, shared=3)]

    found = await ListRelationships(cases, relationships).execute(
        case_id, LECTORA, ReviewStatus.SUGGESTED
    )

    assert [(v.entity_a.entity_id, v.entity_b.entity_id) for v in found.items] == [(1, 3), (1, 2)]
    assert found.counts == {
        ReviewStatus.SUGGESTED: 2,
        ReviewStatus.CONFIRMED: 0,
        ReviewStatus.DISCARDED: 0,
    }
    assert relationships.saved == []


async def test_confirmar_un_sugerido_lo_guarda_con_firma_y_no_se_repite() -> None:
    cases, _, relationships, case_id = await setup()
    relationships.views[case_id] = [suggested(1, 2, shared=2)]
    review = ReviewRelationship(cases, relationships)
    key = RelationshipKey(1, 2, APPEARS)

    view, changed = await review.execute(case_id, key, ReviewStatus.CONFIRMED, BENJI)
    _, again = await review.execute(case_id, key, ReviewStatus.CONFIRMED, BENJI)

    assert (changed, again) == (True, False)
    assert (view.review_status, view.reviewed_by, view.origin) == (
        ReviewStatus.CONFIRMED,
        "benji",
        Origin.COOCCURRENCE,
    )
    (saved,) = relationships.saved
    _, write, audit = saved
    # Un calculado se guarda por primera vez, con su confianza de ese momento.
    assert (write.relationship_id, write.confidence) == (None, 0.7)
    assert audit.action == InvestigationAction.RELATIONSHIP_CONFIRMED
    assert audit.payload["before"] == "suggested"
    assert audit.payload["shared_articles"] == 0


async def test_descartar_y_lo_que_no_se_puede_revisar() -> None:
    cases, _, relationships, case_id = await setup()
    relationships.views[case_id] = [suggested(1, 2)]
    review = ReviewRelationship(cases, relationships)
    key = RelationshipKey(1, 2, APPEARS)

    view, _ = await review.execute(case_id, key, ReviewStatus.DISCARDED, BENJI)

    assert view.review_status is ReviewStatus.DISCARDED
    assert relationships.saved[0][2].action == InvestigationAction.RELATIONSHIP_DISCARDED
    with pytest.raises(RelationshipValidationError):
        await review.execute(case_id, key, ReviewStatus.SUGGESTED, BENJI)
    with pytest.raises(RelationshipNotFoundError):
        await review.execute(case_id, RelationshipKey(1, 3, APPEARS), ReviewStatus.CONFIRMED, BENJI)
    with pytest.raises(CaseForbiddenError):
        await review.execute(case_id, key, ReviewStatus.CONFIRMED, LECTORA)


async def test_un_vinculo_dibujado_nace_confirmado_con_confianza_uno() -> None:
    cases, entities, relationships, case_id = await setup()
    create = CreateRelationship(cases, entities, relationships)

    view, created = await create.execute(
        case_id, RelationshipInput(2, 1, "family", notes=" primos "), BENJI
    )

    assert created is True
    # «Familiar» es simétrico: se guarda con el id menor primero.
    assert view.key == RelationshipKey(1, 2, RelationshipType.FAMILY)
    assert (view.origin, view.confidence, view.review_status, view.notes) == (
        Origin.HUMAN,
        1.0,
        ReviewStatus.CONFIRMED,
        "primos",
    )
    audit = relationships.saved[0][2]
    assert audit.action == InvestigationAction.RELATIONSHIP_CREATED
    assert audit.actor == BENJI


async def test_un_vinculo_dirigido_respeta_el_sentido() -> None:
    cases, entities, relationships, case_id = await setup()

    view, _ = await CreateRelationship(cases, entities, relationships).execute(
        case_id, RelationshipInput(3, 1, "owns"), BENJI
    )

    assert view.key == RelationshipKey(3, 1, RelationshipType.OWNS)


async def test_dibujar_uno_que_ya_sugeria_el_sistema_lo_confirma_sin_duplicar() -> None:
    cases, entities, relationships, case_id = await setup()
    relationships.views[case_id] = [suggested(1, 2, shared=3)]
    create = CreateRelationship(cases, entities, relationships)

    view, created = await create.execute(case_id, RelationshipInput(1, 2, "appears_with"), BENJI)
    _, again = await create.execute(case_id, RelationshipInput(1, 2, "appears_with"), BENJI)

    assert (created, again) == (True, False)
    assert len(relationships.views[case_id]) == 1
    # Conserva su origen: lo vio el sistema y lo confirmó una persona.
    assert (view.origin, view.confidence) == (Origin.COOCCURRENCE, 0.9)
    assert relationships.saved[0][2].action == InvestigationAction.RELATIONSHIP_CONFIRMED


async def test_solo_entre_entidades_confirmadas_del_caso() -> None:
    cases, entities, relationships, case_id = await setup()
    create = CreateRelationship(cases, entities, relationships)

    with pytest.raises(RelationshipValidationError, match="confirmadas"):
        await create.execute(case_id, RelationshipInput(1, 4, "associate"), BENJI)
    with pytest.raises(RelationshipValidationError, match="confirmadas"):
        await create.execute(case_id, RelationshipInput(1, 99, "associate"), BENJI)
    with pytest.raises(RelationshipValidationError, match="etiqueta"):
        await create.execute(case_id, RelationshipInput(1, 2, "custom"), BENJI)
    with pytest.raises(InvalidRequestError, match="consigo misma"):
        await create.execute(case_id, RelationshipInput(1, 1, "associate"), BENJI)
    with pytest.raises(CaseForbiddenError):
        await create.execute(case_id, RelationshipInput(1, 2, "associate"), LECTORA)
    assert relationships.saved == []


async def test_en_un_caso_cerrado_no_se_vincula() -> None:
    cases, entities, relationships, case_id = await setup()
    await UpdateCase(cases).execute(case_id, CaseChanges(status=CaseStatus.CLOSED), BENJI)

    with pytest.raises(CaseClosedError):
        await CreateRelationship(cases, entities, relationships).execute(
            case_id, RelationshipInput(1, 2, "associate"), BENJI
        )
