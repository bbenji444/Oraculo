"""Reglas puras de los reportes: nivel de las subregiones y qué cae dentro (§15)."""

import pytest

from app.domain.aggregates import AggregateLevel, NoteLocation
from app.domain.geocoding import Precision
from app.domain.region import RegionLevel
from app.domain.reports import is_inside, subregion_level
from app.domain.search import SearchStatus


def note(code: str, country: str = "MEX") -> NoteLocation:
    # La precisión no importa para saber si está dentro.
    return NoteLocation(code, country, Precision.MUNICIPALITY)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (RegionLevel.COUNTRY, AggregateLevel.STATE),
        (RegionLevel.STATE, AggregateLevel.MUNICIPALITY),
        (RegionLevel.MUNICIPALITY, AggregateLevel.LOCALITY),
        # Una localidad no tiene subregiones: se cuenta a sí misma.
        (RegionLevel.LOCALITY, AggregateLevel.LOCALITY),
    ],
)
def test_las_subregiones_son_el_nivel_de_abajo(
    level: RegionLevel, expected: AggregateLevel
) -> None:
    assert subregion_level(level, "MEX" if level is RegionLevel.COUNTRY else "14") is expected


def test_otro_pais_se_cuenta_a_si_mismo() -> None:
    # El catálogo solo tiene estados de México.
    assert subregion_level(RegionLevel.COUNTRY, "COL") is AggregateLevel.COUNTRY
    assert is_inside(note("COL", "COL"), "COL", RegionLevel.COUNTRY)
    assert not is_inside(note("MEX", "MEX"), "COL", RegionLevel.COUNTRY)


def test_dentro_de_un_estado_por_el_prefijo_de_la_clave() -> None:
    assert is_inside(note("14039"), "14", RegionLevel.STATE)  # Guadalajara en Jalisco
    assert is_inside(note("14"), "14", RegionLevel.STATE)  # solo "Jalisco"
    assert not is_inside(note("16053"), "14", RegionLevel.STATE)  # Morelia
    assert not is_inside(note("16"), "14", RegionLevel.STATE)  # solo "Michoacán"
    assert is_inside(note("140390001"), "14039", RegionLevel.MUNICIPALITY)


def test_lo_de_otro_pais_nunca_esta_dentro_de_mexico() -> None:
    assert is_inside(note("17"), "MEX", RegionLevel.COUNTRY)
    assert not is_inside(note("FRA", "FRA"), "MEX", RegionLevel.COUNTRY)
    # "México" a secas no se sabe si es Jalisco: cuenta como de fuera.
    assert not is_inside(note("MEX"), "14", RegionLevel.STATE)


def test_una_localidad_se_contiene_a_si_misma() -> None:
    assert is_inside(note("140390001"), "140390001", RegionLevel.LOCALITY)


@pytest.mark.parametrize(
    ("status", "finished"),
    [
        (SearchStatus.PENDING, False),
        (SearchStatus.RUNNING, False),
        (SearchStatus.COMPLETED, True),
        (SearchStatus.PARTIAL, True),
        (SearchStatus.FAILED, True),
    ],
)
def test_solo_una_busqueda_terminada_tiene_reporte(status: SearchStatus, finished: bool) -> None:
    assert status.is_finished is finished
