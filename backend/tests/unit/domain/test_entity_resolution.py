"""Reglas puras para reconocer a la misma entidad escrita de otra forma (Fase 9.5).

Los nombres son inventados: las pruebas no guardan datos de personas reales.
"""

import pytest

from app.domain.entity_resolution import entity_name_norm


@pytest.mark.parametrize(
    "written",
    ["Julián N", "Julián “N”", "Julián 'N'", "Julián «N»", 'Julián "N"', "julián  ‘N’"],
)
def test_las_comillas_no_separan_un_nombre(written: str) -> None:
    # En las notas mexicanas «Julián “N”» es la forma normal de nombrar a un
    # detenido; cada medio usa otras comillas.
    assert entity_name_norm(written) == "JULIAN N"


def test_se_conserva_la_regla_del_proyecto() -> None:
    # Mayúsculas, sin acentos, con Ñ y sin espacios repetidos (CLAUDE.md §6.3).
    assert entity_name_norm("  Peña   Nieto ") == "PEÑA NIETO"


def test_una_comilla_dentro_de_una_palabra_la_parte_igual_en_todas_sus_formas() -> None:
    assert entity_name_norm("O'Higgins") == entity_name_norm("O’Higgins") == "O HIGGINS"


def test_solo_comillas_queda_vacio() -> None:
    assert entity_name_norm(" “” '' ") == ""
