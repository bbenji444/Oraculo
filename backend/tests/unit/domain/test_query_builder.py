"""Constructor de consultas: casos de la especificación §7.2 y del ADR-0009."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.domain.concept import ConceptDraft
from app.domain.errors import ConceptValidationError, InvalidRequestError, QueryTooLongError
from app.domain.queries import (
    CountryFilter,
    DateWindow,
    PlaceFacts,
    Provider,
    QueryPlace,
    place_for,
)
from app.domain.query_builder import build_queries
from app.domain.query_dialects import DIALECTS, GOOGLE_MAX_WORDS, gdelt_country
from app.domain.region import RegionLevel

TODAY = date(2026, 10, 16)
WEEK = DateWindow.last_days(7, TODAY)
MEXICO = CountryFilter("México", "MX", "MX", "Mexico")
COLOMBIA = CountryFilter("Colombia", "CO", "CO", "Colombia")
NORWAY = CountryFilter("Noruega", "NO", None, "Norway")
CDMX_TERMS = ("Ciudad de México", "CDMX")

CIBERSEGURIDAD = ConceptDraft.validated(
    name="Ciberseguridad",
    description="Ataques informáticos, robo de datos y fraudes digitales",
    keywords=("ciberataque", "hackeo", "ransomware", "filtración de datos", "phishing"),
    exclude_terms=("curso", "webinar", "diplomado"),
    color="#2E86DE",
)
SPEC_BASE = (
    '(ciberataque OR hackeo OR ransomware OR "filtración de datos" OR phishing) '
    "Iztapalapa -curso -webinar -diplomado"
)


def facts(
    level: RegionLevel,
    name: str,
    *,
    search_terms: tuple[str, ...] = (),
    repeated: bool = False,
    state: str | None = None,
    state_terms: tuple[str, ...] = (),
    country: CountryFilter = MEXICO,
) -> PlaceFacts:
    return PlaceFacts(level, name, search_terms, repeated, state, state_terms, country)


IZTAPALAPA = place_for(
    facts(RegionLevel.MUNICIPALITY, "Iztapalapa", state="Ciudad de México", state_terms=CDMX_TERMS)
)


def texts(place: QueryPlace, window: DateWindow = WEEK) -> dict[Provider, list[str]]:
    result: dict[Provider, list[str]] = {}
    for query in build_queries(CIBERSEGURIDAD, place, window):
        result.setdefault(query.provider, []).append(query.text)
    return result


# --- Casos de la especificación §7.2 (Ciberseguridad · Iztapalapa · 7 días) ---


def test_searchapi_caso_de_la_especificacion() -> None:
    assert texts(IZTAPALAPA)[Provider.SEARCHAPI] == [SPEC_BASE]


def test_google_news_rss_agrega_when_7d() -> None:
    assert texts(IZTAPALAPA)[Provider.GOOGLE_NEWS_RSS] == [f"{SPEC_BASE} when:7d"]


def test_gdelt_con_exclusiones_idioma_y_pais_fips() -> None:
    assert texts(IZTAPALAPA)[Provider.GDELT] == [f"{SPEC_BASE} sourcelang:spanish sourcecountry:MX"]


def test_una_consulta_por_proveedor_con_pais_idioma_fechas_y_creditos() -> None:
    queries = build_queries(CIBERSEGURIDAD, IZTAPALAPA, WEEK)

    assert [q.provider for q in queries] == list(Provider)
    assert {q.language for q in queries} == {"es"}
    assert {q.country for q in queries} == {MEXICO}
    assert {q.window for q in queries} == {WEEK}
    # Solo SearchApi cuesta; RSS, GDELT, el índice y BrowserWork son gratis.
    assert [q.estimated_credits for q in queries] == [1, 0, 0, 0, 0, 0]
    assert queries[0].keywords == CIBERSEGURIDAD.keywords


def test_browserwork_usa_la_sintaxis_de_google_y_google2_acota_fechas() -> None:
    # ADR-0028: Bing no tiene filtro de fecha en el texto; Google web sí
    # (after:/before:, y before: excluye su día).
    bing, google2 = (
        build_queries(CIBERSEGURIDAD, IZTAPALAPA, WEEK, [p])[0].text
        for p in (Provider.BROWSERWORK_BING, Provider.BROWSERWORK_GOOGLE2)
    )
    base = (
        '(ciberataque OR hackeo OR ransomware OR "filtración de datos" OR phishing) '
        "Iztapalapa -curso -webinar -diplomado"
    )

    assert bing == base
    assert google2 == (
        f"{base} after:{WEEK.date_from.isoformat()} "
        f"before:{(WEEK.date_to + timedelta(days=1)).isoformat()}"
    )


def test_se_pueden_pedir_solo_algunos_proveedores() -> None:
    queries = build_queries(CIBERSEGURIDAD, IZTAPALAPA, WEEK, [Provider.GDELT])

    assert [q.provider for q in queries] == [Provider.GDELT]


# --- Cómo se nombra el lugar (ADR-0009) ---


def test_pais_seleccionado_no_agrega_lugar_al_texto() -> None:
    mexico = place_for(facts(RegionLevel.COUNTRY, "México"))

    assert texts(mexico)[Provider.SEARCHAPI] == [
        '(ciberataque OR hackeo OR ransomware OR "filtración de datos" OR phishing) '
        "-curso -webinar -diplomado"
    ]


def test_cdmx_se_busca_con_sus_terminos_curados() -> None:
    cdmx = place_for(facts(RegionLevel.STATE, "Ciudad de México", search_terms=CDMX_TERMS))

    assert '("Ciudad de México" OR CDMX) -curso' in texts(cdmx)[Provider.SEARCHAPI][0]


def test_el_estado_de_mexico_nunca_se_busca_como_mexico_a_secas() -> None:
    edomex = place_for(
        facts(RegionLevel.STATE, "México", search_terms=("Estado de México", "Edomex"))
    )

    text = texts(edomex)[Provider.SEARCHAPI][0]
    assert '("Estado de México" OR Edomex)' in text
    assert " México " not in text


def test_municipio_con_nombre_repetido_lleva_su_estado() -> None:
    benito_juarez = place_for(
        facts(RegionLevel.MUNICIPALITY, "Benito Juárez", repeated=True, state="Quintana Roo")
    )

    assert '"Benito Juárez" "Quintana Roo" -curso' in texts(benito_juarez)[Provider.SEARCHAPI][0]


def test_alcaldia_repetida_lleva_los_terminos_curados_de_la_cdmx() -> None:
    place = place_for(
        facts(
            RegionLevel.MUNICIPALITY,
            "Benito Juárez",
            repeated=True,
            state="Ciudad de México",
            state_terms=CDMX_TERMS,
        )
    )

    assert place.required_terms == CDMX_TERMS


def test_municipio_con_nombre_unico_no_lleva_estado() -> None:
    assert IZTAPALAPA.required_terms == ()


def test_localidad_siempre_lleva_su_estado() -> None:
    place = place_for(facts(RegionLevel.LOCALITY, "San Juan", state="Jalisco"))

    assert (place.terms, place.required_terms) == (("San Juan",), ("Jalisco",))


def test_municipio_con_terminos_curados_los_usa_en_lugar_del_nombre() -> None:
    neza = place_for(
        facts(RegionLevel.MUNICIPALITY, "Nezahualcóyotl", search_terms=("Nezahualcóyotl", "Neza"))
    )

    assert neza.terms == ("Nezahualcóyotl", "Neza")


# --- Formato y dialectos ---


def test_una_sola_palabra_clave_va_sin_parentesis() -> None:
    concept = ConceptDraft.validated(
        name="Secuestro", description="", keywords=("secuestro",), exclude_terms=(), color="#E74C3C"
    )

    [query] = build_queries(concept, IZTAPALAPA, WEEK, [Provider.SEARCHAPI])

    assert query.text == "secuestro Iztapalapa"


def test_exclusion_de_varias_palabras_va_entre_comillas() -> None:
    concept = ConceptDraft.validated(
        name="Robo de vehículos",
        description="",
        keywords=("robo de auto",),
        exclude_terms=("seguro de auto",),
        color="#9B59B6",
    )

    [query] = build_queries(concept, IZTAPALAPA, WEEK, [Provider.SEARCHAPI])

    assert query.text == '"robo de auto" Iztapalapa -"seguro de auto"'


def test_rango_de_fechas_fijas_en_google_news_rss() -> None:
    window = DateWindow.between(date(2026, 10, 1), date(2026, 10, 15))

    [text] = texts(IZTAPALAPA, window)[Provider.GOOGLE_NEWS_RSS]

    # before: excluye su fecha: se usa el día siguiente al último del rango.
    assert text.endswith("after:2026-10-01 before:2026-10-16")


FGR = ConceptDraft.validated(
    name="Fiscalía General de la República",
    description="Actuación de la FGR federal",
    keywords=("Fiscalía General de la República", "FGR"),
    exclude_terms=(),
    color="#1F6FEB",
)
NATIONAL = place_for(facts(RegionLevel.COUNTRY, "México"))


def test_google_news_rss_se_parte_por_palabra_y_por_dia_en_ventanas_cortas() -> None:
    # Medido el 27/10/2026: con OR la consulta llegaba al tope de 100 notas;
    # partida así trajo 281 distintas.
    window = DateWindow.between(date(2026, 10, 25), date(2026, 10, 26))

    queries = build_queries(FGR, NATIONAL, window, [Provider.GOOGLE_NEWS_RSS])

    assert [q.text for q in queries] == [
        '"Fiscalía General de la República" after:2026-10-25 before:2026-10-26',
        '"Fiscalía General de la República" after:2026-10-26 before:2026-10-27',
        "FGR after:2026-10-25 before:2026-10-26",
        "FGR after:2026-10-26 before:2026-10-27",
    ]
    assert [q.keywords for q in queries] == [
        ("Fiscalía General de la República",),
        ("Fiscalía General de la República",),
        ("FGR",),
        ("FGR",),
    ]
    # El adaptador filtra con la ventana completa: no pierde lo que Google
    # fecha en el día de al lado.
    assert {q.window for q in queries} == {window}


def test_google_news_rss_ultimos_dias_se_parte_solo_por_palabra() -> None:
    # when:2d cuenta horas hacia atrás: no se puede partir en días de calendario.
    window = DateWindow.last_days(2, TODAY)

    queries = build_queries(FGR, NATIONAL, window, [Provider.GOOGLE_NEWS_RSS])

    assert [q.text for q in queries] == [
        '"Fiscalía General de la República" when:2d',
        "FGR when:2d",
    ]


def test_google_news_rss_ventana_larga_se_parte_solo_por_palabra() -> None:
    window = DateWindow.between(date(2026, 10, 1), date(2026, 10, 15))

    texts_ = [q.text for q in build_queries(FGR, NATIONAL, window, [Provider.GOOGLE_NEWS_RSS])]

    assert texts_ == [
        '"Fiscalía General de la República" after:2026-10-01 before:2026-10-16',
        "FGR after:2026-10-01 before:2026-10-16",
    ]


def test_google_news_rss_con_muchas_palabras_vuelve_a_una_consulta_con_or() -> None:
    # Cinco palabras en «últimos 7 días»: por palabra no caben en 4 consultas.
    [query] = build_queries(CIBERSEGURIDAD, IZTAPALAPA, WEEK, [Provider.GOOGLE_NEWS_RSS])

    assert query.keywords == CIBERSEGURIDAD.keywords


def test_dos_palabras_en_tres_dias_parten_por_dia_con_or() -> None:
    # 2 palabras x 3 días = 6 > 4: se parte por día con las palabras juntas.
    window = DateWindow.between(date(2026, 10, 24), date(2026, 10, 26))

    queries = build_queries(FGR, NATIONAL, window, [Provider.GOOGLE_NEWS_RSS])

    assert [q.text for q in queries] == [
        '("Fiscalía General de la República" OR FGR) after:2026-10-24 before:2026-10-25',
        '("Fiscalía General de la República" OR FGR) after:2026-10-25 before:2026-10-26',
        '("Fiscalía General de la República" OR FGR) after:2026-10-26 before:2026-10-27',
    ]


def test_solo_google_news_rss_se_parte_y_no_usa_cache() -> None:
    window = DateWindow.between(date(2026, 10, 25), date(2026, 10, 26))

    providers = [q.provider for q in build_queries(FGR, NATIONAL, window)]

    assert providers.count(Provider.GOOGLE_NEWS_RSS) == 4
    assert all(providers.count(p) == 1 for p in Provider if p is not Provider.GOOGLE_NEWS_RSS)
    assert DIALECTS[Provider.GOOGLE_NEWS_RSS].cacheable is False


def test_colombia_filtra_por_su_fips_en_gdelt() -> None:
    colombia = place_for(facts(RegionLevel.COUNTRY, "Colombia", country=COLOMBIA))

    assert texts(colombia)[Provider.GDELT][0].endswith("sourcecountry:CO")


def test_pais_sin_fips_usa_su_nombre_en_ingles_sin_espacios() -> None:
    usa_sin_fips = CountryFilter("Estados Unidos", "US", None, "United States of America")

    assert gdelt_country(QueryPlace((), (), NORWAY)) == "norway"
    assert gdelt_country(QueryPlace((), (), usa_sin_fips)) == "unitedstatesofamerica"


def test_consulta_larga_se_reparte_sin_perder_ni_repetir_palabras() -> None:
    keywords = tuple(f"palabra{i}" for i in range(40))
    concept = ConceptDraft.validated(
        name="Largo", description="", keywords=keywords, exclude_terms=(), color="#000000"
    )

    queries = build_queries(concept, IZTAPALAPA, WEEK, [Provider.SEARCHAPI])

    assert len(queries) > 1
    assert all(len(q.text.split()) <= GOOGLE_MAX_WORDS for q in queries)
    assert tuple(k for q in queries for k in q.keywords) == keywords


def test_si_ni_una_palabra_cabe_es_error_claro() -> None:
    concept = ConceptDraft.validated(
        name="Imposible",
        description="",
        keywords=("ataque",),
        exclude_terms=tuple(f"excluir{i}" for i in range(GOOGLE_MAX_WORDS)),
        color="#000000",
    )

    with pytest.raises(QueryTooLongError, match="Reduce las exclusiones"):
        build_queries(concept, IZTAPALAPA, WEEK, [Provider.SEARCHAPI])


def test_concepto_sin_palabras_clave_es_error() -> None:
    class Empty:
        keywords: tuple[str, ...] = ()
        exclude_terms: tuple[str, ...] = ()

    with pytest.raises(ConceptValidationError):
        build_queries(Empty(), IZTAPALAPA, WEEK)


# --- Rango de fechas ---


def test_ultimos_dias_y_su_descripcion() -> None:
    assert (WEEK.date_from, WEEK.date_to) == (date(2026, 10, 9), TODAY)
    assert WEEK.describe() == "últimos 7 días"
    assert DateWindow.last_days(1, TODAY).describe() == "último día"


def test_rango_fijo_y_su_descripcion() -> None:
    window = DateWindow.between(date(2026, 10, 1), date(2026, 10, 15))

    assert window.describe() == "del 01/10/2026 al 15/10/2026"


@pytest.mark.parametrize("days", [0, 91])
def test_ultimos_dias_fuera_de_rango(days: int) -> None:
    with pytest.raises(InvalidRequestError, match="1 a 90"):
        DateWindow.last_days(days, TODAY)


def test_rango_fijo_al_reves_o_demasiado_largo() -> None:
    with pytest.raises(InvalidRequestError, match="anterior"):
        DateWindow.between(date(2026, 10, 15), date(2026, 10, 1))
    with pytest.raises(InvalidRequestError, match="90 días"):
        DateWindow.between(date(2026, 1, 1), date(2026, 10, 1))


def test_un_momento_cae_o_no_dentro_del_rango_en_hora_local() -> None:
    mexico = timezone(timedelta(hours=-6))
    window = DateWindow.between(date(2026, 10, 8), date(2026, 10, 14))

    # 15 de octubre a las 03:00 UTC sigue siendo 14 de octubre en la CDMX.
    assert window.contains(datetime(2026, 10, 15, 3, 0, tzinfo=UTC), mexico)
    assert not window.contains(datetime(2026, 10, 15, 7, 0, tzinfo=UTC), mexico)
    assert not window.contains(datetime(2026, 10, 7, 23, 0, tzinfo=mexico), mexico)


# --- Índice local (ADR-0013) ---


def test_indice_local_se_describe_en_palabras() -> None:
    assert texts(IZTAPALAPA)[Provider.LOCAL_INDEX] == [
        'contiene: ciberataque, hackeo, ransomware, "filtración de datos" o phishing'
        " · lugar: Iztapalapa · sin: curso, webinar o diplomado"
    ]


def test_indice_local_con_estado_requerido_estado_y_pais() -> None:
    juarez = place_for(
        facts(RegionLevel.MUNICIPALITY, "Benito Juárez", repeated=True, state="Quintana Roo")
    )
    jalisco = place_for(PlaceFacts(RegionLevel.STATE, "Jalisco", (), False, None, (), MEXICO, "14"))
    mexico = place_for(facts(RegionLevel.COUNTRY, "México"))

    assert 'lugar: "Benito Juárez" (y "Quintana Roo") ·' in texts(juarez)[Provider.LOCAL_INDEX][0]
    assert "lugar: Jalisco ·" in texts(jalisco)[Provider.LOCAL_INDEX][0]
    assert "lugar: México" in texts(mexico)[Provider.LOCAL_INDEX][0]


def test_las_consultas_llevan_exclusiones_y_lugar_aparte() -> None:
    [query] = build_queries(CIBERSEGURIDAD, IZTAPALAPA, WEEK, [Provider.LOCAL_INDEX])

    assert query.exclude_terms == CIBERSEGURIDAD.exclude_terms
    assert query.place == IZTAPALAPA
    assert DIALECTS[Provider.LOCAL_INDEX].cacheable is False
    assert DIALECTS[Provider.SEARCHAPI].cacheable is True
