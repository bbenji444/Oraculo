"""Reglas de una búsqueda completa (§9): estado final y "dentro de la región"."""

import pytest

from app.domain.search import SearchStatus, Stage, StageCount, final_status, in_region
from tests.unit import fake_gazetteer as cat


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
