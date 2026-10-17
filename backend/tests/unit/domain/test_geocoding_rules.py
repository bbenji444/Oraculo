"""Reglas puras del geolocalizador (bordes que no cubren los casos de §11)."""

import pytest

from app.application.use_cases.geocoding import GeocodeMentions
from app.domain.geocoding import (
    UNKNOWN_CONFIDENCE,
    Choice,
    Mention,
    MentionRole,
    Precision,
    Resolution,
    disambiguate,
    is_mexico_name,
    mark_primary,
    most_general,
)
from tests.unit import fake_gazetteer as cat


def test_sin_candidatos_no_hay_eleccion() -> None:
    assert most_general([]) == []
    assert disambiguate([], [], None) == Choice(None, None, UNKNOWN_CONFIDENCE)


def test_un_pais_contiene_todo_lo_suyo_y_no_tiene_estado() -> None:
    assert cat.MEXICO.contains(cat.IZTAPALAPA)
    assert not cat.MEXICO.contains(cat.SPAIN)
    assert not cat.MEXICO.contains(cat.MEXICO)
    assert cat.MEXICO.state_code is None
    assert cat.SPAIN.state_code is None


def test_dos_paises_sin_desempate_quedan_sin_ubicar() -> None:
    assert disambiguate([cat.MEXICO, cat.SPAIN], [], None).place is None


def test_quien_cuenta_como_pais_mexico() -> None:
    assert is_mexico_name("México")
    assert not is_mexico_name("Edomex")
    assert not Mention("x", MentionRole.EVENT, country="  ").is_abroad
    assert not Mention("x", MentionRole.EVENT, country="México").is_abroad
    assert Mention("x", MentionRole.EVENT, country="Colombia").is_abroad


def test_sin_lugar_del_hecho_no_hay_principal() -> None:
    mentioned = Resolution(
        Mention("Neza", MentionRole.MENTIONED), cat.NEZA, Precision.MUNICIPALITY, 0.95
    )

    assert mark_primary([mentioned], 0.6) == [mentioned]


class StatelessGazetteer(cat.FakeGazetteer):
    """Catálogo al que le falta la región del estado (para el estado común)."""

    async def by_code(self, code: str) -> cat.Place | None:
        return None


@pytest.mark.anyio
async def test_si_el_estado_comun_no_esta_en_el_catalogo_queda_sin_ubicar() -> None:
    use_case = GeocodeMentions(StatelessGazetteer())

    [result] = await use_case.run(
        [Mention("San Pedro", MentionRole.EVENT, state_hint="Coahuila")], cat.COAHUILA
    )

    # Con la pista queda un solo candidato: no hace falta el estado común.
    assert result.place == cat.SAN_PEDRO_COAH
    [ambiguous] = await use_case.run(
        [Mention("San Pedro", MentionRole.EVENT, state_hint="Puebla")], None
    )
    assert ambiguous.place is None
