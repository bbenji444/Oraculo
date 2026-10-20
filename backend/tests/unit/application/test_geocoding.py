"""Geolocalizador: los casos obligatorios de la especificación §11 y algunos más."""

import pytest

from app.application.use_cases.geocoding import GeocodeMentions
from app.domain.geocoding import (
    EXACT_CONFIDENCE,
    NEIGHBORHOOD_EXACT_CONFIDENCE,
    NEIGHBORHOOD_FAMILY_CONFIDENCE,
    STATE_FALLBACK_CONFIDENCE,
    STATE_HINT_CONFIDENCE,
    TIEBREAK_CONFIDENCE,
    Mention,
    MentionRole,
    Precision,
    Resolution,
    disambiguate,
)
from app.domain.region import RegionLevel
from tests.unit import fake_gazetteer as cat

pytestmark = pytest.mark.anyio

EVENT = MentionRole.EVENT
MENTIONED = MentionRole.MENTIONED


async def resolve(*mentions: Mention, searched: cat.Place | None = None) -> list[Resolution]:
    return await GeocodeMentions(cat.FakeGazetteer()).run(list(mentions), searched)


async def one(mention: Mention, searched: cat.Place | None = None) -> Resolution:
    [result] = await resolve(mention, searched=searched)
    return result


# --- Casos obligatorios de §11 ---


async def test_iztapalapa_es_la_alcaldia_no_la_localidad() -> None:
    result = await one(Mention("Iztapalapa", EVENT))

    assert result.place == cat.IZTAPALAPA
    assert result.place is not None and result.place.display_name == "Alcaldía Iztapalapa"
    assert (result.precision, result.confidence) == (Precision.MUNICIPALITY, EXACT_CONFIDENCE)
    assert result.is_primary


async def test_san_pedro_garza_garcia_es_nuevo_leon() -> None:
    result = await one(Mention("San Pedro Garza García", EVENT))

    assert result.place == cat.SAN_PEDRO_GG


async def test_san_pedro_con_coahuila_en_la_nota_es_coahuila() -> None:
    san_pedro, _ = await resolve(Mention("San Pedro", EVENT), Mention("Coahuila", MENTIONED))

    assert san_pedro.place == cat.SAN_PEDRO_COAH
    assert san_pedro.confidence == TIEBREAK_CONFIDENCE


async def test_san_pedro_sin_pista_es_ambiguo_y_no_se_ubica() -> None:
    result = await one(Mention("San Pedro", EVENT))

    assert (result.place, result.precision) == (None, Precision.UNKNOWN)
    assert result.confidence < 0.6
    assert not result.is_primary


@pytest.mark.parametrize("text", ["CDMX", "la capital del país"])
async def test_cdmx_y_la_capital_del_pais_son_el_estado_09(text: str) -> None:
    result = await one(Mention(text, EVENT))

    assert (result.place, result.precision) == (cat.CDMX, Precision.STATE)


async def test_edomex_es_el_estado_15() -> None:
    assert (await one(Mention("Edomex", EVENT))).place == cat.EDOMEX


@pytest.mark.parametrize("text", ["Nezahualcóyotl", "Neza"])
async def test_nezahualcoyotl_y_neza(text: str) -> None:
    assert (await one(Mention(text, EVENT))).place == cat.NEZA


async def test_madrid_en_espana_es_el_pais_espana() -> None:
    result = await one(Mention("Madrid", EVENT, country="España"), searched=cat.CDMX)

    assert (result.place, result.precision) == (cat.SPAIN, Precision.COUNTRY)


async def test_penon_de_los_banos_conserva_la_enie() -> None:
    result = await one(Mention("Peñón de los Baños", EVENT))

    assert result.place == cat.PENON


async def test_sin_lugar_no_hay_ubicacion() -> None:
    assert await resolve() == []


# --- Más reglas ---


async def test_mexico_el_pais_no_cuenta_como_estado_de_mexico() -> None:
    # Si "México" contara como el estado 15, desempataría hacia el Edomex.
    san_pedro, _ = await resolve(Mention("San Pedro", EVENT), Mention("México", MENTIONED))

    assert san_pedro.place is None


async def test_la_region_buscada_desempata() -> None:
    result = await one(Mention("San Pedro", EVENT), searched=cat.NUEVO_LEON)

    assert result.place == cat.SAN_PEDRO_GG
    assert result.confidence == TIEBREAK_CONFIDENCE


async def test_la_pista_de_estado_de_la_ia_filtra() -> None:
    result = await one(Mention("San Pedro", EVENT, state_hint="Coahuila"))

    assert result.place == cat.SAN_PEDRO_COAH


async def test_ambiguo_dentro_de_un_estado_sube_al_estado() -> None:
    # Un municipio y una localidad del mismo estado sin desempate posible:
    # no se elige ninguno, pero se sabe el estado.

    choice = disambiguate([cat.SAN_PEDRO_COAH, cat.SAN_PEDRO_COAH_LOC], [], None)

    assert (choice.place, choice.state_code) == (None, "05")
    assert choice.confidence == STATE_FALLBACK_CONFIDENCE


async def test_nombre_mal_escrito_se_acepta_con_confianza_reducida() -> None:
    result = await one(Mention("Iztapalpa", EVENT))

    assert result.place == cat.IZTAPALAPA
    assert result.confidence < EXACT_CONFIDENCE


async def test_la_principal_es_el_lugar_del_hecho_mas_especifico() -> None:
    results = await resolve(
        Mention("Ciudad de México", EVENT),
        Mention("Iztapalapa", EVENT),
        Mention("Neza", MENTIONED),
    )

    assert [r.is_primary for r in results] == [False, True, False]


async def test_la_ia_puede_sugerir_el_nivel() -> None:
    result = await one(Mention("México", EVENT, kind_hint=RegionLevel.STATE))

    assert result.place == cat.EDOMEX


async def test_un_pais_que_no_esta_en_el_catalogo_no_se_ubica() -> None:
    result = await one(Mention("Lugar", EVENT, country="Atlántida"))

    assert (result.place, result.precision) == (None, Precision.UNKNOWN)


async def test_una_mencion_vacia_no_se_ubica() -> None:
    assert (await one(Mention("  ", EVENT))).place is None


async def test_dos_localidades_del_mismo_estado_suben_al_estado() -> None:
    # Dos localidades "San Pedro" en Coahuila: no se sabe cuál, pero sí el estado.
    result = await one(
        Mention("San Pedro", EVENT, kind_hint=RegionLevel.LOCALITY, state_hint="Coahuila")
    )

    assert (result.place, result.precision) == (cat.COAHUILA, Precision.STATE)
    assert result.confidence == STATE_FALLBACK_CONFIDENCE


# --- Fallas de la primera búsqueda real (17/10/2026) ---


async def test_juchitan_de_zaragoza_es_el_de_oaxaca_por_su_alias() -> None:
    result = await one(Mention("Juchitán de Zaragoza", EVENT))

    assert result.place == cat.JUCHITAN_OAX
    assert result.precision is Precision.MUNICIPALITY


async def test_juchitan_a_secas_se_desempata_por_el_estado_de_la_nota() -> None:
    juchitan, _oaxaca = await resolve(Mention("Juchitán", MENTIONED), Mention("Oaxaca", MENTIONED))

    assert juchitan.place == cat.JUCHITAN_OAX
    assert juchitan.confidence == TIEBREAK_CONFIDENCE


async def test_localidad_de_otro_estado_no_se_usa_si_la_nota_nombra_sus_estados() -> None:
    gloria, juchitan, *_states = await resolve(
        Mention("colonia La Gloria", EVENT),
        Mention("Juchitán de Zaragoza", EVENT),
        Mention("Oaxaca", MENTIONED),
        Mention("Chiapas", MENTIONED),
    )

    # Antes: la colonia de Juchitán se ubicaba en un pueblo de Guanajuato.
    assert gloria.place is None
    assert gloria.precision is Precision.UNKNOWN
    assert juchitan.place == cat.JUCHITAN_OAX
    assert juchitan.is_primary


async def test_localidad_unica_sin_estados_en_la_nota_si_se_usa() -> None:
    # Sin estados de contexto no hay con qué contrastar: se conserva (§11, Peñón).
    result = await one(Mention("Colonia la Gloria", EVENT))

    assert result.place == cat.LA_GLORIA_GTO


async def test_municipio_de_otro_estado_si_se_conserva() -> None:
    # Una nota de Jalisco puede mencionar un municipio de otro estado sin
    # nombrar ese estado: los municipios no se descartan.
    juchitan, _jalisco = await resolve(
        Mention("Juchitán de Zaragoza", MENTIONED), Mention("Chiapas", MENTIONED)
    )

    assert juchitan.place == cat.JUCHITAN_OAX


# --- Errores reales del historial (20/10/2026) ---


async def test_polanco_de_la_cdmx_no_cae_en_la_localidad_de_jalisco() -> None:
    # La IA dijo "Polanco, Ciudad de México" y la nota también nombraba Jalisco.
    # Antes, sin Polanco en INEGI para la CDMX, se olvidaba el estado y ganaba
    # Jalisco. Ahora es la colonia de OpenStreetMap, en Miguel Hidalgo.
    polanco, _ = await resolve(
        Mention("Polanco", EVENT, RegionLevel.LOCALITY, state_hint="Ciudad de México"),
        Mention("Jalisco", MENTIONED, RegionLevel.STATE),
    )

    assert polanco.place is not None
    assert (polanco.place.region_id, polanco.place.detail) == (
        cat.MIGUEL_HIDALGO.region_id,
        "Polanco",
    )
    assert polanco.precision is Precision.LOCALITY
    assert polanco.confidence == NEIGHBORHOOD_EXACT_CONFIDENCE
    assert polanco.is_primary


async def test_un_lugar_que_no_es_colonia_conocida_queda_en_el_estado_de_la_ia() -> None:
    # "calle Molière": ni INEGI ni las colonias la tienen; se sabe que es la CDMX.
    result = await one(Mention("calle Molière", EVENT, RegionLevel.LOCALITY, state_hint="CDMX"))

    assert result.place == cat.CDMX
    assert result.precision is Precision.STATE
    assert result.confidence == STATE_HINT_CONFIDENCE
    assert result.is_primary


async def test_colonia_por_familia_y_sin_pista_de_estado_usa_el_de_la_busqueda() -> None:
    result = await one(Mention("colonia Roma", EVENT), searched=cat.CDMX)

    assert result.place is not None and result.place.detail == "Colonia Roma Norte"
    assert result.confidence == NEIGHBORHOOD_FAMILY_CONFIDENCE


async def test_colonia_en_varias_alcaldias_es_ambigua_salvo_que_la_ia_diga_cual() -> None:
    ambiguous = await one(Mention("colonia Centro", EVENT, state_hint="CDMX"))
    hinted = await one(
        Mention("colonia Centro", EVENT, state_hint="CDMX", municipality_hint="alcaldía Iztapalapa")
    )

    assert ambiguous.place == cat.CDMX
    assert hinted.place is not None
    assert (hinted.place.region_id, hinted.precision) == (
        cat.IZTAPALAPA.region_id,
        Precision.LOCALITY,
    )


async def test_dos_bocas_de_tabasco_no_cae_en_veracruz() -> None:
    result = await one(Mention("Dos Bocas", MENTIONED, RegionLevel.LOCALITY, state_hint="Tabasco"))

    assert result.place == cat.TABASCO


@pytest.mark.parametrize(
    "text", ["alcaldía Iztapalapa", "Alcaldía Iztapalapa", "delegación Iztapalapa"]
)
async def test_la_palabra_alcaldia_no_impide_encontrar_el_municipio(text: str) -> None:
    result = await one(Mention(text, EVENT, RegionLevel.MUNICIPALITY, state_hint="CDMX"))

    assert result.place == cat.IZTAPALAPA


async def test_colonia_y_calle_se_quitan_antes_de_buscar() -> None:
    result = await one(Mention("colonia Peñón de los Baños", EVENT, state_hint="CDMX"))

    assert result.place == cat.PENON


async def test_estado_de_mexico_no_se_confunde_con_el_pais() -> None:
    result = await one(Mention("Estado de México", MENTIONED, RegionLevel.STATE))

    assert result.place == cat.EDOMEX


async def test_la_principal_prefiere_el_lugar_del_hecho_dentro_de_la_region_buscada() -> None:
    # Nota de Guanajuato que también narra un hecho en Iztapalapa: buscando en
    # la CDMX, la ubicación útil es la de Iztapalapa.
    results = await resolve(
        Mention("Guanajuato", EVENT, RegionLevel.STATE),
        Mention("Iztapalapa", EVENT, RegionLevel.MUNICIPALITY, state_hint="CDMX"),
        searched=cat.CDMX,
    )

    assert [r.is_primary for r in results] == [False, True]


async def test_sin_lugar_del_hecho_se_usa_el_mencionado_dentro_de_la_region() -> None:
    # La IA marcó todo como "mencionado" (13 de 24 notas sin ubicación).
    results = await resolve(
        Mention("Nuevo León", MENTIONED, RegionLevel.STATE),
        Mention("Iztapalapa", MENTIONED, RegionLevel.MUNICIPALITY, state_hint="CDMX"),
        searched=cat.CDMX,
    )

    assert [r.is_primary for r in results] == [False, True]


async def test_sin_lugar_del_hecho_ni_mencion_en_la_region_queda_sin_ubicar() -> None:
    results = await resolve(Mention("Nuevo León", MENTIONED, RegionLevel.STATE), searched=cat.CDMX)

    assert not any(r.is_primary for r in results)


async def test_con_municipio_de_la_ia_no_vale_la_colonia_homonima_de_otra_alcaldia() -> None:
    # "Ajusco, Tlalpan" caía en la Colonia Ajusco de Coyoacán. Aquí: "Roma"
    # con municipio Iztapalapa no es la Roma Norte de Cuauhtémoc.
    result = await one(
        Mention("colonia Roma", EVENT, state_hint="CDMX", municipality_hint="Iztapalapa")
    )

    assert result.place == cat.IZTAPALAPA
    assert result.precision is Precision.MUNICIPALITY
    assert result.confidence == TIEBREAK_CONFIDENCE


async def test_un_parque_que_nadie_tiene_queda_en_el_municipio_que_dice_la_ia() -> None:
    result = await one(
        Mention(
            "Parque Bicentenario",
            EVENT,
            RegionLevel.LOCALITY,
            "CDMX",
            municipality_hint="Iztapalapa",
        )
    )

    assert (result.place, result.precision) == (cat.IZTAPALAPA, Precision.MUNICIPALITY)


async def test_el_rosario_de_las_notas_es_el_municipio_rosario_de_inegi() -> None:
    result = await one(Mention("El Rosario", EVENT, RegionLevel.MUNICIPALITY, state_hint="Sinaloa"))

    assert result.place == cat.ROSARIO_SIN


async def test_el_nombre_completo_con_articulo_gana_si_existe() -> None:
    # "La Gloria" no se recorta: existe tal cual (localidad "Colonia la Gloria").
    result = await one(Mention("colonia La Gloria", EVENT, state_hint="Guanajuato"))

    assert result.place == cat.LA_GLORIA_GTO
