"""Eliminar y restaurar casos y búsquedas, con repositorios en memoria (27/10/2026)."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from app.application.audit import SEARCH_DELETED, SEARCH_RESTORED, Actor
from app.application.ports.search_reads import SearchOwnership
from app.application.use_cases.cases import (
    AddCaseMember,
    CaseInput,
    CreateCase,
    GetCase,
    ListCases,
)
from app.application.use_cases.run_search import SearchNotFoundError
from app.application.use_cases.trash import DeleteCase, DeleteSearch, RestoreCase, RestoreSearch
from app.domain.errors import CaseForbiddenError, CaseNotFoundError, SearchForbiddenError
from app.domain.investigation import CaseStatus, InvestigationAction
from app.domain.search import SearchTrigger
from tests.unit.fake_cases import FakeCaseRepository

pytestmark = pytest.mark.anyio

BENJI = Actor("benji", "127.0.0.1")
OTRA = Actor("otra-analista", "127.0.0.1")
POLANCO = CaseInput("Homicidio estilista Polanco", "Caso Micky Hair", "normal")


@pytest.fixture
def repo() -> FakeCaseRepository:
    return FakeCaseRepository()


async def test_el_dueno_elimina_el_caso_y_deja_de_verse_para_todos(
    repo: FakeCaseRepository,
) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case
    await AddCaseMember(repo).execute(case.id, "otra-analista", "editor", BENJI)

    await DeleteCase(repo).execute(case.id, BENJI)

    with pytest.raises(CaseNotFoundError):
        await GetCase(repo).execute(case.id, BENJI)
    with pytest.raises(CaseNotFoundError):
        await GetCase(repo).execute(case.id, OTRA)
    page = await ListCases(repo).execute(BENJI)
    assert page.items == ()
    # Se queda en la base con la fecha: es reversible.
    assert repo.cases[case.id].deleted_at is not None
    entry = repo.audit[-1][1]
    assert entry.action == InvestigationAction.CASE_DELETED
    assert entry.payload == {"name": "Homicidio estilista Polanco", "status": "open"}


async def test_solo_el_dueno_elimina(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case
    await AddCaseMember(repo).execute(case.id, "otra-analista", "editor", BENJI)

    with pytest.raises(CaseForbiddenError):
        await DeleteCase(repo).execute(case.id, OTRA)
    assert repo.cases[case.id].deleted_at is None


async def test_deshacer_devuelve_el_caso_como_estaba(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case
    await DeleteCase(repo).execute(case.id, BENJI)

    restored = await RestoreCase(repo).execute(case.id, BENJI)

    assert restored.case.deleted_at is None
    assert restored.case.status is CaseStatus.OPEN
    assert (await GetCase(repo).execute(case.id, BENJI)).case.name == POLANCO.name
    assert repo.audit[-2][1].action == InvestigationAction.CASE_RESTORED


async def test_eliminar_dos_veces_es_como_si_no_existiera(repo: FakeCaseRepository) -> None:
    case = (await CreateCase(repo).execute(POLANCO, BENJI)).case
    await DeleteCase(repo).execute(case.id, BENJI)

    with pytest.raises(CaseNotFoundError):
        await DeleteCase(repo).execute(case.id, BENJI)


@dataclass
class FakeTrash:
    """Papelera de búsquedas en memoria."""

    owners: dict[UUID, SearchOwnership] = field(default_factory=dict)
    calls: list[tuple[UUID, bool, str, str]] = field(default_factory=list)

    async def ownership(self, search_id: UUID) -> SearchOwnership | None:
        return self.owners.get(search_id)

    async def set_deleted(
        self, search_id: UUID, *, deleted: bool, actor_id: str, ip: str | None, action: str
    ) -> None:
        owner = self.owners[search_id]
        self.owners[search_id] = SearchOwnership(owner.user_id, owner.trigger, deleted)
        self.calls.append((search_id, deleted, actor_id, action))


def _trash_with(trigger: SearchTrigger, owner: str = "benji") -> tuple[FakeTrash, UUID]:
    trash = FakeTrash()
    search_id = uuid4()
    trash.owners[search_id] = SearchOwnership(owner, trigger, deleted=False)
    return trash, search_id


async def test_quitar_mi_busqueda_del_historial_y_deshacerlo() -> None:
    trash, search_id = _trash_with(SearchTrigger.MANUAL)

    await DeleteSearch(trash).execute(search_id, BENJI)
    await RestoreSearch(trash).execute(search_id, BENJI)

    assert trash.calls == [
        (search_id, True, "benji", SEARCH_DELETED),
        (search_id, False, "benji", SEARCH_RESTORED),
    ]
    assert trash.owners[search_id].deleted is False


async def test_las_corridas_automaticas_las_puede_quitar_cualquiera() -> None:
    trash, search_id = _trash_with(SearchTrigger.AUTOMATIC, owner="sistema")

    await DeleteSearch(trash).execute(search_id, OTRA)

    assert trash.owners[search_id].deleted is True


async def test_la_busqueda_manual_de_otra_persona_no_se_quita() -> None:
    trash, search_id = _trash_with(SearchTrigger.MANUAL, owner="benji")

    with pytest.raises(SearchForbiddenError):
        await DeleteSearch(trash).execute(search_id, OTRA)
    assert trash.calls == []


async def test_una_busqueda_que_no_existe_o_ya_se_quito() -> None:
    trash, search_id = _trash_with(SearchTrigger.MANUAL)
    await DeleteSearch(trash).execute(search_id, BENJI)

    with pytest.raises(SearchNotFoundError):
        await DeleteSearch(trash).execute(search_id, BENJI)
    with pytest.raises(SearchNotFoundError):
        await DeleteSearch(trash).execute(uuid4(), BENJI)
    # Restaurar una que no estaba eliminada no escribe nada.
    trash2, other = _trash_with(SearchTrigger.MANUAL)
    await RestoreSearch(trash2).execute(other, BENJI)
    assert trash2.calls == []
