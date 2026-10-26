"""El muro de un caso y «Mis casos» con repositorios en memoria (Fase 9.6, H9.3)."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.audit import Actor
from app.application.ports.case_graph import CaseOnMap, GraphPoints, NoteSource
from app.application.ports.entities import CaseEntity
from app.application.use_cases.case_graph import GetCaseGraph, ListCasesOnMap
from app.domain.case_graph import GeoPoint
from app.domain.errors import CaseNotFoundError
from app.domain.investigation import EntityType, InvestigationAction, LegalStatus, ReviewStatus
from tests.unit.application.test_entities_use_cases import BENJI, LECTORA, mention, new_case, person
from tests.unit.fake_cases import FakeCaseRepository
from tests.unit.fake_entities import FakeEntityRepository
from tests.unit.fake_relationships import FakeRelationshipRepository, suggested

pytestmark = pytest.mark.anyio

MIGUEL_HIDALGO = GeoPoint(-99.2, 19.43)
POLANCO = GeoPoint(-99.19, 19.433)


@dataclass
class FakePoints:
    """``CaseGraphRepositoryPort`` en memoria."""

    entity_points: dict[int, GeoPoint] = field(default_factory=dict)
    notes: tuple[NoteSource, ...] = ()
    cases: list[CaseOnMap] = field(default_factory=list)

    async def points(self, case_id: UUID, entity_ids: list[int]) -> GraphPoints:
        wanted = {i: p for i, p in self.entity_points.items() if i in entity_ids}
        return GraphPoints(wanted, self.notes)

    async def cases_on_map(self, user_id: str) -> list[CaseOnMap]:
        return list(self.cases)


def confirmed(entity: CaseEntity, kind: EntityType = EntityType.PERSON) -> CaseEntity:
    legal = LegalStatus.ALLEGED if kind is EntityType.PERSON else None
    return replace(entity, type=kind, review_status=ReviewStatus.CONFIRMED, legal_status=legal)


def note(article_id: int, point: GeoPoint | None = MIGUEL_HIDALGO) -> NoteSource:
    return NoteSource(
        article_id, f"Nota {article_id}", f"https://medio.mx/{article_id}", None, point
    )


async def world(max_nodes: int = 150) -> tuple[GetCaseGraph, FakeCaseRepository, UUID]:
    cases, entities, relationships = (
        FakeCaseRepository(),
        FakeEntityRepository(),
        FakeRelationshipRepository(),
    )
    case_id = await new_case(cases)
    # Personas 1 y 2 confirmadas en las notas 10 y 11; la 3 sigue sugerida.
    entities.add_entity(case_id, confirmed(person(1, mentions=2)))
    entities.add_entity(case_id, confirmed(person(2, mentions=1)))
    entities.add_entity(case_id, person(3))
    place = replace(person(4, mentions=1), label="Polanco")
    entities.add_entity(case_id, confirmed(place, EntityType.PLACE))
    relationships.views[case_id] = [
        suggested(1, 2),
        replace(suggested(1, 3), review_status=ReviewStatus.SUGGESTED),
        replace(suggested(2, 4), review_status=ReviewStatus.DISCARDED),
    ]
    points = FakePoints({4: POLANCO}, (note(10), note(11), note(12, None)))
    use_case = GetCaseGraph(
        cases=cases,
        entities=entities,
        relationships=relationships,
        points=points,
        max_nodes=max_nodes,
    )
    return use_case, cases, case_id


async def test_el_muro_solo_dibuja_confirmadas_con_su_posicion() -> None:
    use_case, _, case_id = await world()

    graph = await use_case.execute(case_id, LECTORA)

    by_id = {n.entity.entity_id: n for n in graph.nodes}
    assert set(by_id) == {1, 2, 4}  # la 3 está sugerida: no entra (ADR-0104)
    assert (by_id[4].position, by_id[4].pinned) == (POLANCO, True)
    assert by_id[1].pinned is False
    assert by_id[1].position != by_id[2].position  # repartidas, no encimadas
    assert graph.name == "Homicidio estilista Polanco"
    # Solo vínculos entre visibles y no descartados.
    assert [(e.entity_a.entity_id, e.entity_b.entity_id) for e in graph.edges] == [(1, 2)]
    assert by_id[1].first_seen == datetime(2026, 10, 1, tzinfo=UTC)
    assert by_id[1].last_seen == datetime(2026, 10, 2, tzinfo=UTC)


async def test_la_constelacion_une_las_notas_ubicadas() -> None:
    use_case, _, case_id = await world()

    graph = await use_case.execute(case_id, BENJI)

    assert [n.article_id for n in graph.notes] == [10, 11]  # la 12 no está ubicada
    # La nota 10 tiene a 1, 2 y Polanco; la 11 solo a 1: comparten una.
    assert graph.note_links == {(10, 11): 1}
    assert graph.center == MIGUEL_HIDALGO


async def test_abrir_el_muro_cuenta_como_ver_el_caso() -> None:
    use_case, cases, case_id = await world()

    await use_case.execute(case_id, BENJI)
    await use_case.execute(case_id, BENJI)

    views = [e for _, e, _ in cases.audit if e.action == InvestigationAction.CASE_VIEWED]
    assert len(views) == 1  # una vez cada 5 minutos por persona
    assert views[0].payload == {"view": "wall"}
    with pytest.raises(CaseNotFoundError):
        await use_case.execute(case_id, Actor("extrano"))


async def test_el_tope_deja_fuera_a_las_menos_mencionadas() -> None:
    use_case, _, case_id = await world(max_nodes=2)

    graph = await use_case.execute(case_id, BENJI)

    assert {n.entity.entity_id for n in graph.nodes} == {1, 2}
    assert graph.hidden_nodes == 1


async def test_mis_casos_solo_trae_los_ubicados_por_nombre() -> None:
    located = CaseOnMap(uuid4(), "Zeta", "normal", 3, 1, MIGUEL_HIDALGO)
    other = CaseOnMap(uuid4(), "alfa", "restricted", 2, 0, POLANCO)
    lost = CaseOnMap(uuid4(), "Sin notas", "normal", 0, 0, None)

    found = await ListCasesOnMap(FakePoints(cases=[located, lost, other])).execute(BENJI)

    assert [c.name for c in found] == ["alfa", "Zeta"]


def test_las_menciones_de_prueba_tienen_fecha() -> None:
    # Guardia: las fechas de arriba salen de `mention` (día 1 + n de octubre).
    assert mention(10, 1, None, 0).published_at == datetime(2026, 10, 1, tzinfo=UTC)
