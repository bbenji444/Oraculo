"""RelocateSearch: volver a ubicar sin la IA, con piezas en memoria."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from app.application.audit import Actor
from app.application.ports.llm import EnrichmentError, EnrichmentResult
from app.application.ports.search_store import ArticleMentions, StoredText
from app.application.use_cases.geocoding import GeocodeMentions
from app.application.use_cases.relocate import RelocateSearch, ReprocessSearch
from app.application.use_cases.run_search import PipelineLimits, SearchNotFoundError
from app.cli import reubicar
from app.domain.enrichment import LLMUsage
from app.domain.errors import NotFoundError, ProviderUnavailableError
from app.domain.geocoding import Mention, MentionRole, Resolution
from tests.unit import fake_gazetteer as cat
from tests.unit.application.test_run_search import LLM, Searches, enrichment, stored_search

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
    # En una búsqueda de un estado, sin lugar no cuenta como dentro (11/11/2026).
    assert (nothing.after, nothing.in_region) == (None, False)
    assert set(store.saved) == {1, 2}  # la nota sin menciones no se reescribe
    assert store.in_region == {1: False, 2: True, 3: False}
    assert store.progress == {"in_region": 1, "out_of_region": 2, "unlocated": 0}


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
    assert "dentro: 1 · fuera: 2 · sin ubicación: 0" in text
    assert reubicar.describe(None) == "Sin ubicación"
    assert reubicar.parse_args([]).busqueda is None


class TextStore(Store):
    def __init__(self, items: Sequence[ArticleMentions], texts: Sequence[StoredText]) -> None:
        super().__init__(items)
        self.texts = list(texts)
        self.enriched: dict[int, list[Resolution]] = {}
        self.spent: list[tuple[LLMUsage, float, Actor]] = []

    async def search_texts(self, search_id: UUID) -> list[StoredText]:
        return self.texts

    async def save_enrichment(
        self, article_id: int, result: EnrichmentResult, resolutions: Sequence[Resolution]
    ) -> None:
        self.enriched[article_id] = list(resolutions)
        # Como la base: lo nuevo queda como menciones guardadas.
        self.items = [
            replace(i, mentions=tuple(r.mention for r in resolutions))
            if i.article_id == article_id
            else i
            for i in self.items
        ]

    async def add_llm_usage(
        self, search_id: UUID, usage: LLMUsage, cost_usd: float, actor: Actor
    ) -> None:
        self.spent.append((usage, cost_usd, actor))


CUAUTLA_TEXT = StoredText(4, "Una regidora en Cuautla", "Texto de la nota.", None)
CUAUTLA_OLD = ArticleMentions(4, "Una regidora en Cuautla", (Mention("Iztapalapa", EVENT),), None)


async def test_reprocesar_vuelve_a_preguntar_a_la_ia_y_guarda_lo_nuevo() -> None:
    store = TextStore([CUAUTLA_OLD, NOTHING], [CUAUTLA_TEXT])
    searches = Searches(stored_search())
    llm = LLM({CUAUTLA_TEXT.title: enrichment(Mention("Iztapalapa", EVENT, state_hint="CDMX"))})
    gazetteer = cat.FakeGazetteer()

    report = await ReprocessSearch(
        searches=searches,
        store=store,
        gazetteer=gazetteer,
        geocoder=GeocodeMentions(gazetteer),
        llm=llm,
        limits=PipelineLimits(150, 2, 0.10, 0.50),
    ).run(uuid4())

    [relocation] = report.relocations
    assert (relocation.before, relocation.after, relocation.in_region) == (
        None,
        cat.IZTAPALAPA,
        True,
    )
    assert [r.title for r in llm.requests] == [CUAUTLA_TEXT.title]
    assert store.enriched[4][0].mention.state_hint == "CDMX"
    assert (report.usage, report.failed) == (LLMUsage(1000, 100), 0)
    assert store.spent == [(LLMUsage(1000, 100), pytest.approx(0.00015), Actor("benji"))]
    # Al final reubica todo para dejar los conteos al día.
    # La nota sin lugar, en una búsqueda de la CDMX, cuenta como fuera (11/11/2026).
    assert store.progress == {"in_region": 1, "out_of_region": 1, "unlocated": 0}


async def test_reprocesar_registra_las_fallas_y_sigue() -> None:
    other = StoredText(5, "Otra", "Texto.", None)
    store = TextStore([], [CUAUTLA_TEXT, other])
    searches = Searches(stored_search())
    llm = LLM(
        {
            CUAUTLA_TEXT.title: EnrichmentError("JSON inválido", LLMUsage(7, 1)),
            other.title: ProviderUnavailableError("caída", provider="openai"),
        }
    )
    gazetteer = cat.FakeGazetteer()
    use = ReprocessSearch(
        searches=searches,
        store=store,
        gazetteer=gazetteer,
        geocoder=GeocodeMentions(gazetteer),
        llm=llm,
        limits=PipelineLimits(150, 2, 0.10, 0.50),
    )

    report = await use.run(uuid4())

    assert (report.relocations, report.failed, report.usage) == ((), 2, LLMUsage(7, 1))
    assert {e.error_type for e in searches.errors} == {
        "EnrichmentError",
        "ProviderUnavailableError",
    }
    with pytest.raises(SearchNotFoundError):
        await ReprocessSearch(
            searches=Searches(None),
            store=store,
            gazetteer=gazetteer,
            geocoder=GeocodeMentions(gazetteer),
            llm=llm,
            limits=PipelineLimits(150, 2, 0.10, 0.50),
        ).run(uuid4())
    no_region = Searches(replace(stored_search(), region_code="99"))
    with pytest.raises(NotFoundError):
        await ReprocessSearch(
            searches=no_region,
            store=store,
            gazetteer=gazetteer,
            geocoder=GeocodeMentions(gazetteer),
            llm=llm,
            limits=PipelineLimits(150, 2, 0.10, 0.50),
        ).run(uuid4())
