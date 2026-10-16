"""Normalización de nombres (CLAUDE.md §6.3): mayúsculas, sin acentos, con Ñ."""

import unicodedata

import pytest

from app.domain.names import normalize_name


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("Peñón de los Baños", "PEÑON DE LOS BAÑOS"),
        ("Nezahualcóyotl", "NEZAHUALCOYOTL"),
        ("Ciudad de México", "CIUDAD DE MEXICO"),
        ("Ñuu Savi", "ÑUU SAVI"),
        ("Güémez", "GUEMEZ"),
        ("Iztapalapa", "IZTAPALAPA"),
        ("San Pedro Garza García", "SAN PEDRO GARZA GARCIA"),
        ("Cañada Morelos", "CAÑADA MORELOS"),
        ("Dr. Arroyo", "DR. ARROYO"),
    ],
)
def test_normaliza_nombres_reales(original: str, expected: str) -> None:
    assert normalize_name(original) == expected


def test_conserva_la_enie_minuscula_y_mayuscula() -> None:
    assert normalize_name("ñ") == "Ñ"
    assert normalize_name("Ñ") == "Ñ"


def test_la_enie_descompuesta_en_unicode_tambien_se_conserva() -> None:
    # Algunas fuentes guardan la Ñ como "N" + tilde combinable (NFD).
    decomposed = unicodedata.normalize("NFD", "Peñón")
    assert decomposed != "Peñón"

    assert normalize_name(decomposed) == "PEÑON"


def test_el_resultado_queda_en_forma_compuesta() -> None:
    # La Ñ normalizada debe ser un solo carácter para que la base compare igual.
    assert len(normalize_name("ñ")) == 1


def test_una_tilde_que_no_acompana_a_n_se_elimina() -> None:
    assert normalize_name("Ã") == "A"


def test_colapsa_espacios_repetidos_y_recorta() -> None:
    assert normalize_name("  San   Pedro\t Tlaquepaque  ") == "SAN PEDRO TLAQUEPAQUE"


@pytest.mark.parametrize("empty", ["", "   ", "\t\n"])
def test_texto_vacio_da_cadena_vacia(empty: str) -> None:
    assert normalize_name(empty) == ""


def test_es_idempotente() -> None:
    once = normalize_name("Peñón de los Baños")

    assert normalize_name(once) == once
