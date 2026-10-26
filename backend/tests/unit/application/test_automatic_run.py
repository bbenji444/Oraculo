"""Petición de las corridas automáticas del monitor FGR (F12.8, ADR-0031)."""

from datetime import date, datetime

import pytest

from app.application.clock import MEXICO_CITY
from app.application.use_cases.automatic_run import (
    AutomaticProfile,
    AutomaticRunConfigError,
    PrepareAutomaticRun,
)
from app.domain.concept import ConceptDraft
from app.domain.queries import Provider
from app.domain.search import SearchTrigger
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import MEXICO, FakeRegionRepository

pytestmark = pytest.mark.anyio

PROFILE = AutomaticProfile(
    concept="Fiscalía General de la República",
    region_code="MEX",
    sources=(Provider.GOOGLE_NEWS_RSS, Provider.LOCAL_INDEX),
    window_days=1,
    user_id="monitor-automatico",
)
SLOT = datetime(2026, 10, 26, 7, 0, tzinfo=MEXICO_CITY)


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


async def test_busca_la_fgr_en_todo_mexico_hoy_y_ayer_con_fuentes_gratis() -> None:
    repo = concepts_with("Homicidio", "Fiscalia General de la Republica")
    fgr = next(c for c in repo.concepts.values() if c.data.name.startswith("Fiscalia"))

    request = await PrepareAutomaticRun(repo, FakeRegionRepository(), PROFILE).request(
        date(2026, 10, 26), SLOT
    )

    assert request.concept_ids == (fgr.id,)
    assert request.region_id == MEXICO.id
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
        ).request(date(2026, 10, 26), SLOT)


async def test_sin_la_region_no_se_arma() -> None:
    repo = concepts_with("Fiscalia General de la Republica")

    with pytest.raises(AutomaticRunConfigError, match="MEX"):
        await PrepareAutomaticRun(repo, FakeRegionRepository(()), PROFILE).request(
            date(2026, 10, 26), SLOT
        )
