"""Limpieza de las frases que propone la IA (ADR-0109)."""

from typing import cast

import pytest

from app.domain.concept import OPEN_MAX_PHRASES
from app.domain.errors import ConceptValidationError
from app.domain.term_suggestions import (
    MAX_SUGGESTED_EXCLUSIONS,
    EmptySuggestionError,
    clean_suggestion,
    validated_intent,
)


def test_conserva_el_orden_y_limpia_espacios() -> None:
    result = clean_suggestion(
        " Hackeos  a bases de datos ", ["filtran  datos", "hackeo gobierno"], [" curso "]
    )

    assert result.name == "Hackeos a bases de datos"
    assert result.phrases == ("filtran datos", "hackeo gobierno")
    assert result.exclude_terms == ("curso",)


def test_descarta_lo_que_el_formulario_rechazaria() -> None:
    result = clean_suggestion(
        "Robo",
        ['"roban auto"', "roban OR asaltan", "-roban", "x", "roban camioneta", "Roban camióneta"],
        [],
    )

    # Comillas, OR suelto, guion inicial, 1 letra y la repetida sin acento.
    assert result.phrases == ("roban camioneta",)


def test_tope_de_frases_y_de_exclusiones() -> None:
    result = clean_suggestion(
        "Muchas",
        [f"frase {i}" for i in range(OPEN_MAX_PHRASES + 5)],
        [f"fuera {i}" for i in range(MAX_SUGGESTED_EXCLUSIONS + 5)],
    )

    assert len(result.phrases) == OPEN_MAX_PHRASES
    assert result.phrases[0] == "frase 0"
    assert len(result.exclude_terms) == MAX_SUGGESTED_EXCLUSIONS


def test_una_exclusion_igual_a_una_frase_se_quita() -> None:
    result = clean_suggestion("Robo", ["roban auto"], ["Roban auto", "seguro de auto"])

    assert result.exclude_terms == ("seguro de auto",)


def test_sin_frases_utiles_es_error_claro() -> None:
    with pytest.raises(EmptySuggestionError, match="otras palabras"):
        clean_suggestion("Nada", ['"x"', ""], ["curso"])


@pytest.mark.parametrize("name", ["", "x", "y" * 81])
def test_un_nombre_que_no_sirve_queda_vacio(name: str) -> None:
    assert clean_suggestion(name, ["roban auto"], []).name == ""


def test_la_descripcion_se_limpia() -> None:
    assert validated_intent("  hackeos a  bases de datos ") == "hackeos a bases de datos"


@pytest.mark.parametrize("text", ["robo", "", "x" * 501])
def test_descripcion_muy_corta_o_muy_larga(text: str) -> None:
    with pytest.raises(ConceptValidationError) as error:
        validated_intent(text)

    problems = cast(list[dict[str, str]], error.value.details["problemas"])
    assert [p["campo"] for p in problems] == ["description"]
