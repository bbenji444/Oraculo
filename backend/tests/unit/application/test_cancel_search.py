"""Cancelar una búsqueda que todavía corre, con un repositorio en memoria (19/11/2026)."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from app.application.audit import Actor
from app.application.ports.search_reads import SearchOwnership
from app.application.use_cases.cancel_search import CancelSearch
from app.application.use_cases.run_search import SearchNotFoundError
from app.domain.errors import SearchAlreadyFinishedError, SearchForbiddenError
from app.domain.search import SearchTrigger

pytestmark = pytest.mark.anyio

BENJI = Actor("benji", "127.0.0.1")
OTRA = Actor("otra-analista", "127.0.0.1")


@dataclass
class FakeSearches:
    """``SearchCancelPort`` en memoria."""

    owners: dict[UUID, SearchOwnership] = field(default_factory=dict)
    running: set[UUID] = field(default_factory=set)
    calls: list[tuple[UUID, str, str | None]] = field(default_factory=list)

    async def ownership(self, search_id: UUID) -> SearchOwnership | None:
        return self.owners.get(search_id)

    async def cancel(self, search_id: UUID, *, actor_id: str, ip: str | None) -> bool:
        self.calls.append((search_id, actor_id, ip))
        if search_id not in self.running:
            return False
        self.running.discard(search_id)
        return True


def _running(
    trigger: SearchTrigger = SearchTrigger.MANUAL, owner: str = "benji"
) -> tuple[FakeSearches, UUID]:
    search_id = uuid4()
    searches = FakeSearches({search_id: SearchOwnership(owner, trigger, False)}, {search_id})
    return searches, search_id


async def test_quien_la_lanzo_la_cancela_mientras_corre() -> None:
    searches, search_id = _running()

    await CancelSearch(searches).execute(search_id, BENJI)

    assert searches.calls == [(search_id, "benji", "127.0.0.1")]
    assert searches.running == set()


async def test_si_ya_termino_no_hay_nada_que_cancelar() -> None:
    searches, search_id = _running()
    searches.running.clear()

    with pytest.raises(SearchAlreadyFinishedError):
        await CancelSearch(searches).execute(search_id, BENJI)


async def test_la_de_otra_persona_no_se_cancela() -> None:
    searches, search_id = _running(owner="otra-analista")

    with pytest.raises(SearchForbiddenError):
        await CancelSearch(searches).execute(search_id, BENJI)
    assert searches.calls == []


async def test_la_corrida_automatica_no_se_cancela() -> None:
    searches, search_id = _running(SearchTrigger.AUTOMATIC)

    with pytest.raises(SearchForbiddenError, match="automáticas"):
        await CancelSearch(searches).execute(search_id, BENJI)
    assert searches.calls == []


async def test_una_que_no_existe_o_ya_se_quito() -> None:
    searches, search_id = _running()
    searches.owners[search_id] = SearchOwnership("benji", SearchTrigger.MANUAL, True)

    with pytest.raises(SearchNotFoundError):
        await CancelSearch(searches).execute(search_id, BENJI)
    with pytest.raises(SearchNotFoundError):
        await CancelSearch(searches).execute(uuid4(), OTRA)
