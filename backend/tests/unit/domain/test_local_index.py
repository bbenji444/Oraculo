"""Criterios del índice local a partir de una consulta planeada (ADR-0013)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.errors import InvalidRequestError
from app.domain.local_index import MAX_LOCAL_RESULTS, criteria_for, for_body
from app.domain.queries import (
    CountryFilter,
    DateWindow,
    PlaceFacts,
    PlannedQuery,
    Provider,
    QueryPlace,
    place_for,
)
from app.domain.region import RegionLevel

CDMX_TZ = ZoneInfo("America/Mexico_City")
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
GUATEMALA = CountryFilter("Guatemala", "GT", "GT", "Guatemala")
WEEK = DateWindow.last_days(7, date(2026, 10, 16))


def query(
    place: QueryPlace | None,
    keywords: tuple[str, ...] = ("hackeo", "robo de  datos", "Peñón"),
    exclude: tuple[str, ...] = ("curso",),
    country: CountryFilter = MEXICO,
) -> PlannedQuery:
    return PlannedQuery(
        Provider.LOCAL_INDEX, "texto", keywords, country, "es", WEEK, 0, exclude, place
    )


def test_normaliza_igual_que_el_catalogo_conservando_la_enie() -> None:
    criteria = criteria_for(query(QueryPlace(("Iztapalapa",), (), MEXICO)), CDMX_TZ)

    assert criteria.keywords == ("HACKEO", "ROBO DE DATOS", "PEÑON")
    assert criteria.exclusions == ("CURSO",)
    assert criteria.place_terms == ("IZTAPALAPA",)
    assert criteria.limit == MAX_LOCAL_RESULTS


def test_dias_completos_en_hora_de_la_ciudad_de_mexico() -> None:
    criteria = criteria_for(query(None), CDMX_TZ)

    # Del 09/10 a las 00:00 al 17/10 a las 00:00 en la CDMX (UTC-6).
    assert criteria.start == datetime(2026, 10, 9, 6, 0, tzinfo=UTC)
    assert criteria.end == datetime(2026, 10, 17, 6, 0, tzinfo=UTC)


def test_mexico_a_nivel_pais_no_filtra_lugar_y_otro_pais_pide_su_nombre() -> None:
    assert criteria_for(query(QueryPlace((), (), MEXICO)), CDMX_TZ).place_terms == ()
    assert criteria_for(query(None), CDMX_TZ).place_terms == ()
    guatemala = query(QueryPlace((), (), GUATEMALA), country=GUATEMALA)
    assert criteria_for(guatemala, CDMX_TZ).place_terms == ("GUATEMALA",)


def test_nombre_repetido_lleva_el_estado() -> None:
    facts = PlaceFacts(
        RegionLevel.MUNICIPALITY, "Benito Juárez", (), True, "Quintana Roo", (), MEXICO, "23"
    )

    criteria = criteria_for(query(place_for(facts)), CDMX_TZ)

    assert criteria.place_terms == ("BENITO JUAREZ",)
    assert criteria.required_terms == ("QUINTANA ROO",)


def test_un_estado_se_busca_por_su_nombre() -> None:
    # Sin pista de estado de GDELT: ubicaba mal notas de otros estados (ADR-0014).
    facts = PlaceFacts(RegionLevel.STATE, "Jalisco", (), False, None, (), MEXICO, "14")

    criteria = criteria_for(query(place_for(facts)), CDMX_TZ)

    assert criteria.place_terms == ("JALISCO",)
    assert not hasattr(criteria, "state_code")


def test_sin_palabras_clave_utiles_es_error() -> None:
    with pytest.raises(InvalidRequestError, match="palabras clave"):
        criteria_for(query(None, keywords=("  ",)), CDMX_TZ)


def test_en_el_cuerpo_un_termino_largo_se_busca_por_sus_primeras_4_palabras() -> None:
    assert for_body(("HEROICA CIUDAD DE JUCHITAN DE ZARAGOZA", "HACKEO", "HACKEO")) == (
        "HEROICA CIUDAD DE JUCHITAN",
        "HACKEO",
    )
