"""Casos de uso de la resolución de entidades con repositorios en memoria (Fase 9.5).

Lo que importa aquí: el sistema solo sugiere (mirar nunca fusiona), unir y
separar piden permiso de edición y caso abierto, y cada decisión queda en la
bitácora con quién la tomó.
"""

from dataclasses import replace
from uuid import UUID

import pytest

from app.application.audit import Actor
from app.application.ports.entities import CaseEntity, MergeSuggestion
from app.application.use_cases.cases import UpdateCase
from app.application.use_cases.resolution import (
    DismissMerge,
    ListMergeSuggestions,
    MergeEntities,
    SplitEntity,
    UnmergeEntity,
)
from app.domain.case import CaseChanges
from app.domain.entity_resolution import MergeReason
from app.domain.errors import (
    CaseClosedError,
    CaseForbiddenError,
    CaseNotFoundError,
    EntityMergeError,
    EntityNotFoundError,
)
from app.domain.investigation import (
    CaseStatus,
    EntityType,
    InvestigationAction,
    LegalStatus,
    ReviewStatus,
)
from tests.unit.application.test_entities_use_cases import BENJI, LECTORA, new_case, person
from tests.unit.fake_cases import FakeCaseRepository
from tests.unit.fake_entities import FakeEntityRepository

pytestmark = pytest.mark.anyio


def confirmed(entity: CaseEntity) -> CaseEntity:
    return replace(entity, review_status=ReviewStatus.CONFIRMED, legal_status=LegalStatus.ALLEGED)


async def setup(*entities: CaseEntity) -> tuple[FakeCaseRepository, FakeEntityRepository, UUID]:
    cases, repo = FakeCaseRepository(), FakeEntityRepository()
    case_id = await new_case(cases)
    for entity in entities:
        repo.add_entity(case_id, entity)
    return cases, repo, case_id


# --- Sugerencias -----------------------------------------------------------------


async def test_las_sugerencias_proponen_conservar_la_confirmada_y_no_fusionan() -> None:
    one, two, three = person(1, mentions=1), confirmed(person(2, mentions=1)), person(3, 3)
    cases, repo, case_id = await setup(one, two, three)
    repo.suggestions = [
        MergeSuggestion(one, three, frozenset({MergeReason.SIMILAR_NAME})),
        MergeSuggestion(one, two, frozenset({MergeReason.SHARED_NAME, MergeReason.SAME_NAME})),
    ]

    # Un lector también las ve.
    found = await ListMergeSuggestions(cases, repo).execute(case_id, LECTORA)

    # Lo más seguro primero: «mismo nombre» antes que «nombre parecido».
    assert [(p.reason, p.first.entity_id, p.second.entity_id) for p in found] == [
        (MergeReason.SAME_NAME, 1, 2),
        (MergeReason.SIMILAR_NAME, 1, 3),
    ]
    # Queda la confirmada; si ninguna lo está, la de más menciones.
    assert [p.keep_id for p in found] == [2, 3]
    # Mirar nunca fusiona ni escribe la bitácora.
    assert (repo.merged_into, repo.resolution_audits) == ({}, [])


async def test_un_extrano_no_ve_las_sugerencias() -> None:
    cases, repo, case_id = await setup(person(1))

    with pytest.raises(CaseNotFoundError):
        await ListMergeSuggestions(cases, repo).execute(case_id, Actor("extrano"))


# --- Fusionar --------------------------------------------------------------------


async def test_son_la_misma_une_con_firma_y_bitacora() -> None:
    cases, repo, case_id = await setup(confirmed(person(1, mentions=2)), person(2, mentions=1))

    kept = await MergeEntities(cases, repo).execute(case_id, 1, 2, BENJI)

    assert kept.entity_id == 1
    assert len(kept.mentions) == 3
    assert [m.entity_id for m in kept.merged] == [2]
    assert await repo.get_entity(case_id, 2) is None
    (audit,) = repo.resolution_audits
    assert audit.action == InvestigationAction.ENTITY_MERGED
    assert audit.actor == BENJI
    assert audit.payload["keep"] == {
        "entity_id": 1,
        "label": "Persona 1",
        "review_status": "confirmed",
        "legal_status": "alleged",
        "mentions": 2,
    }
    assert audit.payload["merged"] == {
        "entity_id": 2,
        "label": "Persona 2",
        "review_status": "suggested",
        "legal_status": None,
        "mentions": 1,
    }


async def test_lo_que_no_se_puede_unir_no_toca_nada() -> None:
    org = replace(person(3), type=EntityType.ORG)
    cases, repo, case_id = await setup(person(1), confirmed(person(2)), org)
    merge = MergeEntities(cases, repo)

    with pytest.raises(EntityMergeError, match="mismo tipo"):
        await merge.execute(case_id, 1, 3, BENJI)
    with pytest.raises(EntityMergeError, match="confirmada"):
        await merge.execute(case_id, 1, 2, BENJI)
    with pytest.raises(EntityNotFoundError):
        await merge.execute(case_id, 1, 99, BENJI)
    with pytest.raises(CaseForbiddenError):
        await merge.execute(case_id, 2, 1, LECTORA)
    assert (repo.merged_into, repo.resolution_audits) == ({}, [])


async def test_no_se_une_dos_veces_ni_en_un_caso_cerrado() -> None:
    cases, repo, case_id = await setup(person(1), person(2), person(3))
    merge = MergeEntities(cases, repo)
    await merge.execute(case_id, 1, 2, BENJI)

    with pytest.raises(EntityMergeError, match="ya está unida"):
        await merge.execute(case_id, 3, 2, BENJI)
    await UpdateCase(cases).execute(case_id, CaseChanges(status=CaseStatus.CLOSED), BENJI)
    with pytest.raises(CaseClosedError):
        await merge.execute(case_id, 1, 3, BENJI)


# --- Deshacer y separar ----------------------------------------------------------


async def test_separar_deshace_la_fusion_con_bitacora() -> None:
    cases, repo, case_id = await setup(person(1), person(2))
    await MergeEntities(cases, repo).execute(case_id, 1, 2, BENJI)
    unmerge = UnmergeEntity(cases, repo)

    separated = await unmerge.execute(case_id, 2, BENJI)

    assert separated.entity_id == 2
    assert await repo.get_entity(case_id, 2) is not None
    audit = repo.resolution_audits[-1]
    assert audit.action == InvestigationAction.ENTITY_UNMERGED
    assert audit.payload == {"entity_id": 2, "was_merged_into": 1}
    with pytest.raises(EntityMergeError, match="no está unida"):
        await unmerge.execute(case_id, 2, BENJI)


async def test_separar_menciones_crea_una_sugerencia_nueva() -> None:
    cases, repo, case_id = await setup(person(1, mentions=3))

    created = await SplitEntity(cases, repo).execute(case_id, 1, [2], BENJI)

    assert created.review_status is ReviewStatus.SUGGESTED
    assert [m.mention_id for m in created.mentions] == [2]
    source = await repo.get_entity(case_id, 1)
    assert source is not None
    assert [m.mention_id for m in source.mentions] == [0, 1]
    audit = repo.resolution_audits[-1]
    assert audit.action == InvestigationAction.ENTITY_SPLIT
    assert audit.payload["mention_ids"] == [2]


async def test_solo_se_separan_menciones_propias_y_nunca_todas() -> None:
    cases, repo, case_id = await setup(person(1, mentions=2), person(2, mentions=1))
    await MergeEntities(cases, repo).execute(case_id, 1, 2, BENJI)
    split = SplitEntity(cases, repo)

    # La mención 0 de la entidad 2 se ve en la 1, pero se separa deshaciendo la fusión.
    kept = await repo.get_entity(case_id, 1)
    assert kept is not None
    assert kept.own_mention_ids == (0, 1)
    with pytest.raises(EntityMergeError, match="deja al menos una"):
        await split.execute(case_id, 1, [0, 1], BENJI)
    with pytest.raises(EntityNotFoundError):
        await split.execute(case_id, 2, [0], BENJI)
    with pytest.raises(CaseForbiddenError):
        await split.execute(case_id, 1, [0], LECTORA)


# --- No son la misma -------------------------------------------------------------


async def test_no_son_la_misma_se_guarda_una_vez_con_el_menor_primero() -> None:
    one, two = person(1), person(2)
    cases, repo, case_id = await setup(one, two)
    repo.suggestions = [MergeSuggestion(one, two, frozenset({MergeReason.SAME_NAME}))]
    dismiss = DismissMerge(cases, repo)

    assert await dismiss.execute(case_id, 2, 1, BENJI) is True
    assert await dismiss.execute(case_id, 1, 2, BENJI) is False

    assert repo.dismissed == {(case_id, 1, 2)}
    assert await ListMergeSuggestions(cases, repo).execute(case_id, BENJI) == []
    (audit,) = repo.resolution_audits
    assert audit.action == InvestigationAction.ENTITY_MERGE_DISMISSED
    with pytest.raises(EntityMergeError):
        await dismiss.execute(case_id, 1, 1, BENJI)
    with pytest.raises(CaseForbiddenError):
        await dismiss.execute(case_id, 1, 2, LECTORA)
