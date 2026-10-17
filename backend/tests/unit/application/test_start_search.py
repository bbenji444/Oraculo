"""StartSearch: validar, crear y encolar; si algo falla no se crea nada."""

from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.ports.search_store import NewSearch
from app.application.use_cases.plan_search import PlanSearch, SearchRequest
from app.application.use_cases.start_search import StartSearch
from app.domain.budget import QueryBudgetExceededError
from app.domain.errors import (
    CreditLimitReachedError,
    LLMNotConfiguredError,
    ServiceUnavailableError,
)
from app.domain.queries import Provider
from tests.unit.application.test_execute_queries import FakeLog
from tests.unit.application.test_plan_search import OPENAI, WEEK, concept
from tests.unit.application.test_run_search import Searches, Source
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import IZTAPALAPA, FakeRegionRepository

pytestmark = pytest.mark.anyio


class Store(Searches):
    def __init__(self) -> None:
        super().__init__(None)
        self.created: list[NewSearch] = []

    async def create(self, search: NewSearch) -> UUID:
        self.created.append(search)
        return uuid4()


class Queue:
    def __init__(self) -> None:
        self.sent: list[UUID] = []

    def enqueue(self, search_id: UUID) -> None:
        self.sent.append(search_id)


def starter(
    *, configured: bool = True, providers: bool = True, used: int = 0, max_queries: int = 10
) -> tuple[StartSearch, Store, Queue, SearchRequest]:
    repo = FakeConceptRepository()
    extorsion = repo.add(concept("Extorsión"))
    sources = (
        [Source(Provider.SEARCHAPI, [], cost=1), Source(Provider.LOCAL_INDEX, [])]
        if providers
        else []
    )
    planner = PlanSearch(
        concepts=repo,
        regions=FakeRegionRepository(),
        providers={s.provider: s for s in sources},
        log=FakeLog(used=used),
        llm=replace(OPENAI, configured=configured),
        llm_max_articles=150,
        credits_limit=100,
    )
    store, queue = Store(), Queue()
    request = SearchRequest("benji", (extorsion.id,), IZTAPALAPA.id, WEEK)
    return StartSearch(planner, store, queue, max_queries), store, queue, request


async def test_crea_la_busqueda_y_la_encola() -> None:
    use, store, queue, request = starter()

    started = await use.execute(request)

    assert queue.sent == [started.search_id]
    [created] = store.created
    assert (created.user_id, created.queries_planned, created.credits_estimated) == (
        "benji",
        2,
        1,
    )
    assert started.estimate.credits == 1


@pytest.mark.parametrize(
    ("options", "error"),
    [
        ({"configured": False}, LLMNotConfiguredError),
        ({"providers": False}, ServiceUnavailableError),
        ({"max_queries": 1}, QueryBudgetExceededError),
        ({"used": 100}, CreditLimitReachedError),
    ],
)
async def test_si_no_se_puede_correr_no_crea_nada(
    options: dict[str, Any], error: type[Exception]
) -> None:
    use, store, queue, request = starter(**options)

    with pytest.raises(error):
        await use.execute(request)

    assert (store.created, queue.sent) == ([], [])
