"""Reglas de una búsqueda completa (§9): estado final y "dentro de la región"."""

import pytest

from app.domain.geocoding import seat_area
from app.domain.region import RegionLevel
from app.domain.search import (
    SearchStatus,
    Stage,
    StageCount,
    final_status,
    in_region,
    outlet_country,
)
from tests.unit import fake_gazetteer as cat
from tests.unit.fake_gazetteer import place


def test_sin_proveedores_que_respondan_la_busqueda_falla() -> None:
    assert final_status(0, 2, ()) is SearchStatus.FAILED


def test_un_proveedor_caido_deja_la_busqueda_parcial() -> None:
    assert final_status(1, 1, ()) is SearchStatus.PARTIAL


@pytest.mark.parametrize(
    ("failed", "expected"), [(5, SearchStatus.COMPLETED), (6, SearchStatus.PARTIAL)]
)
def test_mas_de_la_mitad_de_fallas_en_una_etapa_es_parcial(
    failed: int, expected: SearchStatus
) -> None:
    stages = (StageCount(Stage.EXTRACT, 10, 0), StageCount(Stage.ENRICH, 10, failed))

    assert final_status(2, 0, stages) is expected


def test_una_etapa_sin_notas_no_cuenta_como_falla() -> None:
    assert not StageCount(Stage.ENRICH, 0, 0).failed_too_much


def test_dentro_de_la_region_por_la_clave() -> None:
    assert in_region(cat.IZTAPALAPA, cat.CDMX) is True
    assert in_region(cat.CDMX, cat.CDMX) is True
    assert in_region(cat.NEZA, cat.CDMX) is False
    assert in_region(None, cat.CDMX) is None


def test_dentro_de_un_pais() -> None:
    assert in_region(cat.IZTAPALAPA, cat.MEXICO) is True
    assert in_region(cat.SPAIN, cat.MEXICO) is False


def test_sin_lugar_un_medio_de_otro_pais_cuenta_como_fuera() -> None:
    # Búsqueda del 09/11/2026: «PDI» en México traía decenas de medios .cl sin
    # lugar en la nota (la PDI es la policía de Chile).
    assert in_region(None, cat.MEXICO, "chilevision.cl") is False
    assert in_region(None, cat.CDMX, "rpp.pe") is False
    # Un medio mexicano o uno que no dice su país sigue «sin ubicación».
    assert in_region(None, cat.MEXICO, "eluniversal.com.mx") is None
    assert in_region(None, cat.MEXICO, "milenio.com") is None
    assert in_region(None, cat.MEXICO, None) is None
    # Con ubicación manda la ubicación, no el medio.
    assert in_region(cat.IZTAPALAPA, cat.MEXICO, "chilevision.cl") is True


def test_pais_del_medio_por_su_dominio() -> None:
    assert outlet_country("adnradio.cl") == "CHL"
    assert outlet_country("ELPAIS.ES") == "ESP"
    assert outlet_country("eluniversal.com.mx") == "MEX"
    assert outlet_country("milenio.com") is None
    assert outlet_country("") is None


def test_la_localidad_cabecera_homonima_vale_por_su_municipio() -> None:
    # Búsqueda real del 20/10/2026: "Miguel Hidalgo" era la localidad 090160001,
    # y todo lo ubicado en la alcaldía o en Polanco salía "fuera".
    seat = place(90, "090160001", RegionLevel.LOCALITY, "Miguel Hidalgo")
    other = place(91, "090160002", RegionLevel.LOCALITY, "San Joaquín")

    assert seat_area(seat, cat.MIGUEL_HIDALGO) == cat.MIGUEL_HIDALGO
    assert in_region(cat.MIGUEL_HIDALGO, seat_area(seat, cat.MIGUEL_HIDALGO)) is True
    # Una localidad con otro nombre, o un municipio que no es el suyo, no cambia.
    assert seat_area(other, cat.MIGUEL_HIDALGO) == other
    assert seat_area(seat, cat.IZTAPALAPA) == seat
    assert seat_area(cat.CDMX, None) == cat.CDMX
