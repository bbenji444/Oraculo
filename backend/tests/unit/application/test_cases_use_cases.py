"""Casos de uso de los casos de investigación con un repositorio en memoria (9.3)."""

from uuid import uuid4

import pytest

from app.application.audit import Actor
from app.application.use_cases.cases import (
    CASE_VIEW_DEDUP_MINUTES,
    CaseInput,
    CreateCase,
    GetCase,
    ListCases,
    UpdateCase,
)
from app.domain.case import CaseChanges
from app.domain.errors import (
    CaseClosedError,
    CaseForbiddenError,
    CaseNotFoundError,
    CaseValidationError,
    InvalidRequestError,
)
from app.domain.investigation import CaseMemberRole, CaseStatus, InvestigationAction
from tests.unit.fake_cases import START, FakeCaseRepository

pytestmark = pytest.mark.anyio

BENJI = Actor("benji", "127.0.0.1")
OTRA = Actor("otra-analista", "127.0.0.1")
POLANCO = CaseInput("Homicidio estilista Polanco", "Caso Micky Hair", "restricted")


@pytest.fixture
def repo() -> FakeCaseRepository:
    return FakeCaseRepository()


async def test_crear_un_caso_deja_dueno_y_bitacora(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case

    assert (case.name, case.status, case.sensitivity) == (
        "Homicidio estilista Polanco",
        CaseStatus.OPEN,
        "restricted",
    )
    assert repo.members[case.id] == {"benji": CaseMemberRole.OWNER}
    [(_, entry, _)] = repo.audit
    assert entry.action == InvestigationAction.CASE_CREATED
    assert entry.payload["after"] == {
        "name": "Homicidio estilista Polanco",
        "description": "Caso Micky Hair",
        "status": "open",
        "sensitivity": "restricted",
    }


async def test_datos_invalidos_no_crean_nada(repo: FakeCaseRepository) -> None:
    with pytest.raises(CaseValidationError):
        await CreateCase(repo).execute(CaseInput("  ", "", "secreto"), BENJI)

    assert repo.cases == {}
    assert repo.audit == []


async def test_un_caso_ajeno_no_existe_para_la_otra_persona(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case

    with pytest.raises(CaseNotFoundError) as error:
        await GetCase(repo).execute(case.id, OTRA)
    with pytest.raises(CaseNotFoundError):
        await GetCase(repo).execute(uuid4(), BENJI)

    # El mismo mensaje para "no existe" y "no es tuyo": no se revela nada.
    assert error.value.message == "No existe el caso o no tienes acceso."
    page = await ListCases(repo).execute(OTRA)
    assert page.items == ()


async def test_ver_un_caso_queda_en_la_bitacora_una_vez_por_ventana(
    repo: FakeCaseRepository,
) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case
    use = GetCase(repo)

    await use.execute(case.id, BENJI)
    await use.execute(case.id, BENJI)  # recarga de la pantalla: no se repite
    repo.tick(CASE_VIEW_DEDUP_MINUTES + 1)
    view = await use.execute(case.id, BENJI)

    views = [e for _, e, _ in repo.audit if e.action == InvestigationAction.CASE_VIEWED]
    assert len(views) == 2
    assert view.role is CaseMemberRole.OWNER


async def test_listar_del_mas_reciente_con_cursor_y_sin_archivados(
    repo: FakeCaseRepository,
) -> None:
    create = CreateCase(repo)
    first = (await create.execute(CaseInput("Primero"), BENJI)).case
    second = (await create.execute(CaseInput("Segundo"), BENJI)).case
    third = (await create.execute(CaseInput("Tercero"), BENJI)).case
    await UpdateCase(repo, lambda: START).execute(third.id, CaseChanges(status="archived"), BENJI)
    use = ListCases(repo)

    page = await use.execute(BENJI, limit=1)
    rest = await use.execute(BENJI, cursor=page.next_cursor, limit=5)
    archived = await use.execute(BENJI, status=CaseStatus.ARCHIVED)

    assert [v.case.id for v in page.items + rest.items] == [second.id, first.id]
    assert rest.next_cursor is None
    assert [v.case.id for v in archived.items] == [third.id]
    with pytest.raises(InvalidRequestError):
        await use.execute(BENJI, limit=0)


async def test_cerrar_y_reabrir_mueven_la_fecha_y_la_bitacora(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case
    use = UpdateCase(repo, lambda: START)

    closed = (await use.execute(case.id, CaseChanges(status="closed"), BENJI)).case
    reopened = (await use.execute(case.id, CaseChanges(status="open"), BENJI)).case

    assert (closed.status, closed.closed_at) == (CaseStatus.CLOSED, START)
    assert (reopened.status, reopened.closed_at) == (CaseStatus.OPEN, None)
    actions = [e.action for _, e, _ in repo.audit]
    assert actions[-2:] == [InvestigationAction.CASE_CLOSED, InvestigationAction.CASE_REOPENED]
    assert repo.audit[-2][1].payload["before"] == {
        "name": "Homicidio estilista Polanco",
        "description": "Caso Micky Hair",
        "status": "open",
        "sensitivity": "restricted",
    }


async def test_un_caso_cerrado_no_cambia_sus_datos_pero_se_puede_archivar(
    repo: FakeCaseRepository,
) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case
    use = UpdateCase(repo, lambda: START)
    await use.execute(case.id, CaseChanges(status="closed"), BENJI)

    with pytest.raises(CaseClosedError):
        await use.execute(case.id, CaseChanges(name="Otro nombre"), BENJI)
    archived = (await use.execute(case.id, CaseChanges(status="archived"), BENJI)).case

    # Archivar uno cerrado conserva cuándo se cerró.
    assert (archived.status, archived.closed_at) == (CaseStatus.ARCHIVED, START)


async def test_un_lector_no_edita(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case
    repo.add_member(case.id, "otra-analista", CaseMemberRole.VIEWER)

    view = await GetCase(repo).execute(case.id, OTRA)
    with pytest.raises(CaseForbiddenError):
        await UpdateCase(repo).execute(case.id, CaseChanges(name="Otro"), OTRA)

    assert view.role is CaseMemberRole.VIEWER


async def test_editar_sin_cambios_no_escribe_nada(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case

    same = (await UpdateCase(repo).execute(case.id, CaseChanges(), BENJI)).case

    assert same == case
    assert len(repo.audit) == 1


async def test_un_estado_desconocido_se_rechaza(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case

    with pytest.raises(CaseValidationError):
        await UpdateCase(repo).execute(case.id, CaseChanges(status="borrado"), BENJI)
