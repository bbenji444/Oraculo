"""Consulta de Google web (ADR-0115): una sola, con el literal y el lugar."""

from datetime import date

import pytest

from app.domain.concept import ConceptDraft, QueryMode
from app.domain.errors import QueryTooLongError
from app.domain.queries import (
    CountryFilter,
    DateWindow,
    PlaceFacts,
    Provider,
    QueryPlace,
    place_for,
)
from app.domain.query_builder import build_queries
from app.domain.query_dialects import DIALECTS, GOOGLE_MAX_WORDS
from app.domain.region import RegionLevel

TODAY = date(2026, 11, 18)
WEEK = DateWindow.last_days(7, TODAY)
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
FGR = ConceptDraft.validated(
    name="FGR",
    description="Fiscalía General de la República",
    keywords=("Fiscalía General de la República", "FGR"),
    exclude_terms=("curso",),
    color="#000000",
)
ETERNAL = ConceptDraft.validated(
    name="hacker eternal",
    description="hacker eternal",
    keywords=("hacker eternal", "hackeo Eternal"),
    exclude_terms=(),
    color="#00D2FF",
    query_mode=QueryMode.OPEN,
)
JALISCO = place_for(PlaceFacts(RegionLevel.STATE, "Jalisco", (), False, None, (), MEXICO))
NATIONAL = place_for(PlaceFacts(RegionLevel.COUNTRY, "México", (), False, None, (), MEXICO))
WORLD = place_for(
    PlaceFacts(RegionLevel.WORLD, "Mundo", (), False, None, (), CountryFilter.world("Mundo"))
)


def test_estado_manda_una_consulta_con_el_literal_y_el_lugar() -> None:
    [query] = build_queries(ETERNAL, JALISCO, WEEK, [Provider.SEARCHAPI_WEB])

    assert query.text == "hacker eternal Jalisco"
    assert query.keywords == ("hacker eternal",)
    assert query.exclude_terms == ()
    assert query.estimated_credits == 1
    assert query.window == WEEK


@pytest.mark.parametrize("place", [NATIONAL, WORLD], ids=["pais", "mundo"])
def test_pais_o_mundo_mandan_solo_el_literal(place: QueryPlace) -> None:
    [query] = build_queries(ETERNAL, place, WEEK, [Provider.SEARCHAPI_WEB])

    assert query.text == "hacker eternal"


def test_modo_exacto_tambien_va_sin_or_ni_comillas_ni_exclusiones() -> None:
    [query] = build_queries(FGR, NATIONAL, WEEK, [Provider.SEARCHAPI_WEB])

    assert query.text == "Fiscalía General de la República"


def test_la_subdivision_no_va_en_el_texto_pero_si_para_filtrar() -> None:
    [query] = build_queries(
        FGR, NATIONAL, WEEK, [Provider.SEARCHAPI_WEB], topic_terms=("homicidio", "homicidio")
    )

    assert query.text == "Fiscalía General de la República"
    assert query.topic_terms == ("homicidio",)


def test_google_web_cobra_un_credito_y_comparte_cuenta_con_google_news() -> None:
    web, news = DIALECTS[Provider.SEARCHAPI_WEB], DIALECTS[Provider.SEARCHAPI]

    assert web.credits_per_query == news.credits_per_query == 1
    assert web.credit_account == news.credit_account == "searchapi"
    assert web.cacheable
    assert web.trusts_window and not news.trusts_window
    assert web.render(("FGR",), NATIONAL, (), WEEK, exact=False) == "FGR"


def test_literal_demasiado_largo_es_error_claro() -> None:
    # Una letra por palabra: así caben más de 32 palabras en los 80 caracteres
    # que admite una palabra clave.
    long_text = " ".join("x" * (GOOGLE_MAX_WORDS + 1))
    concept = ConceptDraft.validated(
        name="Largo",
        description="",
        keywords=(long_text,),
        exclude_terms=(),
        color="#000000",
        query_mode=QueryMode.OPEN,
    )

    with pytest.raises(QueryTooLongError):
        build_queries(concept, NATIONAL, WEEK, [Provider.SEARCHAPI_WEB])
