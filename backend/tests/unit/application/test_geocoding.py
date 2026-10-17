"""Geolocalizador: los casos obligatorios de la especificación §11 y algunos más."""

import pytest

from app.application.use_cases.geocoding import GeocodeMentions
from app.domain.geocoding import (
    EXACT_CONFIDENCE,
    STATE_FALLBACK_CONFIDENCE,
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
