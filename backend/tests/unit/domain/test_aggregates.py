"""Conteos para el mapa de calor: subir por la clave INEGI sin inventar precisión."""

import pytest

from app.domain.aggregates import AggregateLevel, NoteLocation, aggregate
from app.domain.geocoding import Precision

NOTES = [
    NoteLocation("14039", "MEX", Precision.MUNICIPALITY),  # Guadalajara
    NoteLocation("141200001", "MEX", Precision.LOCALITY),  # localidad de Zapopan
    NoteLocation("14", "MEX", Precision.STATE),  # solo "Jalisco"
    NoteLocation("17006", "MEX", Precision.MUNICIPALITY),  # Cuautla, Morelos
    NoteLocation("MEX", "MEX", Precision.COUNTRY),  # solo "México"
    NoteLocation("FRA", "FRA", Precision.COUNTRY),  # París
    NoteLocation(None, None, Precision.UNKNOWN),  # sin ubicación
]


def test_por_estado_sube_municipios_y_localidades() -> None:
    result = aggregate(NOTES, AggregateLevel.STATE)

    assert dict(result.counts) == {"14": 3, "17": 1}
    assert (result.coarser, result.abroad, result.unlocated) == (1, 1, 1)
    assert result.total == len(NOTES)


def test_por_municipio_no_reparte_lo_que_solo_tiene_estado() -> None:
    result = aggregate(NOTES, AggregateLevel.MUNICIPALITY)

    assert dict(result.counts) == {"14039": 1, "14120": 1, "17006": 1}
    # "Jalisco" y "México" no se inventan en un municipio.
    assert (result.coarser, result.abroad, result.unlocated) == (2, 1, 1)


def test_por_pais() -> None:
    result = aggregate(NOTES, AggregateLevel.COUNTRY)

    assert dict(result.counts) == {"MEX": 5, "FRA": 1}
    assert (result.coarser, result.abroad, result.unlocated) == (0, 0, 1)


@pytest.mark.parametrize("level", list(AggregateLevel))
def test_sin_notas(level: AggregateLevel) -> None:
    assert aggregate([], level).total == 0
