"""Petición de las corridas automáticas del monitor FGR (F12.8, ADR-0031)."""

from datetime import date, datetime, timedelta

import pytest

from app.application.clock import MEXICO_CITY
from app.application.use_cases.automatic_run import (
    AutomaticProfile,
    AutomaticRunConfigError,
    PrepareAutomaticRun,
)
from app.domain.concept import ConceptDraft
from app.domain.queries import Provider
from app.domain.schedule import RunSchedule, RunWindow
from app.domain.search import SearchTrigger
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import MEXICO, FakeRegionRepository

pytestmark = pytest.mark.anyio

PROFILE = AutomaticProfile(
    concept="Fiscalía General de la República",
    region_code="MEX",
    sources=(Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX),
    user_id="monitor-automatico",
)
SLOT = datetime(2026, 10, 26, 7, 0, tzinfo=MEXICO_CITY)
SCHEDULE = RunSchedule.from_hours((7, 15, 23))


def concepts_with(*names: str) -> FakeConceptRepository:
    repo = FakeConceptRepository()
    for name in names:
        repo.add(
            ConceptDraft.validated(
                name=name,
                description="",
                keywords=("FGR",),
                exclude_terms=(),
                color="#00D2FF",
                is_active=True,
            )
        )
    return repo


async def test_la_de_las_7_busca_la_fgr_en_todo_mexico_solo_desde_las_23() -> None:
    repo = concepts_with("Homicidio", "Fiscalia General de la Republica")
    fgr = next(c for c in repo.concepts.values() if c.data.name.startswith("Fiscalia"))
    last = SLOT - timedelta(hours=8)

    prepare = PrepareAutomaticRun(repo, FakeRegionRepository(), PROFILE)
    request = await prepare.request(SLOT, SCHEDULE)

    assert request.concept_ids == (fgr.id,)
    assert request.region_id == MEXICO.id
    # Benji, 28/10/2026: solo lo publicado desde la corrida anterior (23:00).
    assert request.time_window == RunWindow(last, SLOT)
    # A los buscadores se les piden los dos días que toca la ventana.
    assert (request.window.date_from, request.window.date_to) == (
        date(2026, 10, 25),
        date(2026, 10, 26),
    )
    assert request.providers == (Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX)
    assert (request.trigger, request.scheduled_for) == (SearchTrigger.AUTOMATIC, SLOT)
    assert request.user_id == "monitor-automatico"


async def test_sin_el_concepto_no_se_arma() -> None:
    with pytest.raises(AutomaticRunConfigError, match="make seed"):
        await PrepareAutomaticRun(
            concepts_with("Homicidio"), FakeRegionRepository(), PROFILE
        ).request(SLOT, SCHEDULE)


async def test_sin_la_region_no_se_arma() -> None:
    repo = concepts_with("Fiscalia General de la Republica")

    with pytest.raises(AutomaticRunConfigError, match="MEX"):
        await PrepareAutomaticRun(repo, FakeRegionRepository(()), PROFILE).request(SLOT, SCHEDULE)


async def test_la_de_las_15_pide_solo_el_dia_en_curso() -> None:
    repo = concepts_with("Fiscalia General de la Republica")
    slot = datetime(2026, 10, 26, 15, 0, tzinfo=MEXICO_CITY)

    prepare = PrepareAutomaticRun(repo, FakeRegionRepository(), PROFILE)
    request = await prepare.request(slot, SCHEDULE)

    assert request.time_window == RunWindow(slot - timedelta(hours=8), slot)
    assert (request.window.date_from, request.window.date_to) == (
        date(2026, 10, 26),
        date(2026, 10, 26),
    )


async def test_una_hora_agregada_parte_el_periodo_en_dos() -> None:
    # Benji, 06/11/2026: si agrega las 19:00, esa corrida cubre de 15:00 a 19:00
    # y la de las 23:00 pasa a cubrir de 19:00 a 23:00.
    repo = concepts_with("Fiscalia General de la Republica")
    schedule = RunSchedule.validated((420, 900, 1140, 1380))
    seven_pm = datetime(2026, 10, 26, 19, 0, tzinfo=MEXICO_CITY)
    eleven_pm = datetime(2026, 10, 26, 23, 0, tzinfo=MEXICO_CITY)
    prepare = PrepareAutomaticRun(repo, FakeRegionRepository(), PROFILE)

    new = await prepare.request(seven_pm, schedule)
    night = await prepare.request(eleven_pm, schedule)

    assert new.time_window == RunWindow(datetime(2026, 10, 26, 15, 0, tzinfo=MEXICO_CITY), seven_pm)
    assert night.time_window == RunWindow(seven_pm, eleven_pm)
