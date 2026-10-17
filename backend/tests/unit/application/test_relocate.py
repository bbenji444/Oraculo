"""RelocateSearch: volver a ubicar sin la IA, con piezas en memoria."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from app.application.ports.search_store import ArticleMentions
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.relocate import RelocateSearch
from app.application.use_cases.run_search import SearchNotFoundError
from app.cli import reubicar
from app.domain.errors import NotFoundError
from app.domain.geocoding import Mention, MentionRole, Resolution
from tests.unit import fake_gazetteer as cat
from tests.unit.application.test_run_search import Searches, stored_search

pytestmark = pytest.mark.anyio

EVENT = MentionRole.EVENT
MENTIONED = MentionRole.MENTIONED


class Store:
    def __init__(self, items: Sequence[ArticleMentions]) -> None:
        self.items = list(items)
        self.saved: dict[int, list[Resolution]] = {}
        self.in_region: dict[int, bool | None] = {}
        self.progress: dict[str, object] = {}

    async def search_mentions(self, search_id: UUID) -> list[ArticleMentions]:
        return self.items

    async def save_locations(self, article_id: int, resolutions: Sequence[Resolution]) -> None:
        self.saved[article_id] = list(resolutions)

    async def set_in_region(self, search_id: UUID, article_id: int, in_region: bool | None) -> None:
        self.in_region[article_id] = in_region

    async def merge_progress(self, search_id: UUID, values: Mapping[str, object]) -> None:
        self.progress.update(values)


# Las notas de Oaxaca de la búsqueda real, con lo que se guardó de ellas.
GLORIA = ArticleMentions(
    1,
    "Detienen a dos implicados en el ataque armado",
    (
        Mention("Oaxaca", MENTIONED),
        Mention("Juchitán de Zaragoza", EVENT),
        Mention("colonia La Gloria", EVENT),
    ),
    "110350261",
)
CDMX_NOTE = ArticleMentions(2, "Detienen en Iztapalapa", (Mention("Iztapalapa", EVENT),), "09007")
NOTHING = ArticleMentions(3, "Sin enriquecer", (), None)


def use_case(store: Store, searches: Searches | None = None) -> RelocateSearch:
    gazetteer = cat.FakeGazetteer()
    return RelocateSearch(
        searches or Searches(stored_search()), store, gazetteer, GeocodeMentions(gazetteer)
    )


async def test_reubica_con_las_reglas_vigentes_sin_tocar_las_que_no_cambian() -> None:
    store = Store([GLORIA, CDMX_NOTE, NOTHING])

    gloria, cdmx, nothing = await use_case(store).run(uuid4())

    assert (gloria.before, gloria.after) == (cat.LA_GLORIA_GTO, cat.JUCHITAN_OAX)
    assert gloria.changed
    assert gloria.in_region is False
    assert not cdmx.changed
    assert cdmx.in_region is True
    assert (nothing.after, nothing.in_region) == (None, None)
    assert set(store.saved) == {1, 2}  # la nota sin menciones no se reescribe
    assert store.in_region == {1: False, 2: True, 3: None}
    assert store.progress == {"in_region": 1, "out_of_region": 1, "unlocated": 1}


async def test_busqueda_o_region_inexistentes() -> None:
    no_region = Searches(replace(stored_search(), region_code="99"))

    with pytest.raises(SearchNotFoundError):
        await use_case(Store([]), Searches(None)).run(uuid4())
    with pytest.raises(NotFoundError, match="99"):
        await use_case(Store([]), no_region).run(uuid4())


async def test_el_comando_muestra_antes_y_despues(caplog: pytest.LogCaptureFixture) -> None:
    relocations = await use_case(Store([GLORIA, CDMX_NOTE, NOTHING])).run(uuid4())

    with caplog.at_level(logging.INFO):
        reubicar.show(relocations)

    text = caplog.text
    assert "1 de 3 notas cambiaron de ubicación" in text
    assert "antes:   Colonia la Gloria [110350261]" in text
    assert "después: Heroica Ciudad de Juchitán de Zaragoza [20043] · FUERA de la región" in text
    assert "dentro: 1 · fuera: 1 · sin ubicación: 1" in text
    assert reubicar.describe(None) == "Sin ubicación"
    assert reubicar.parse_args([]).busqueda is None
