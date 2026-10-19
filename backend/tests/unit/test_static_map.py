"""Leyenda y colores del mapa estático del reporte (sin base)."""

import pytest

from app.adapters.reports.static_map import CLASS_FILLS, NO_NOTES_FILL, fill_for, legend


def test_la_leyenda_parte_del_1_al_maximo_en_intervalos_iguales() -> None:
    assert [c.label for c in legend(7)] == ["1", "2", "3–4", "5", "6–7"]
    assert [c.fill for c in legend(7)] == list(CLASS_FILLS)


def test_con_pocas_notas_hay_menos_clases_y_sin_notas_ninguna() -> None:
    assert [c.label for c in legend(2)] == ["1", "2"]
    assert legend(0) == []


@pytest.mark.parametrize(
    ("count", "fill"),
    [(0, NO_NOTES_FILL), (1, CLASS_FILLS[0]), (4, CLASS_FILLS[2]), (7, CLASS_FILLS[4])],
)
def test_cada_subregion_toma_el_color_de_su_clase(count: int, fill: str) -> None:
    assert fill_for(count, 7) == fill
