"""Reglas de un concepto: limpieza, validación y cambios parciales."""

from typing import Any, cast

import pytest

from app.domain.concept import (
    MAX_TERMS,
    NAME_MAX_LENGTH,
    ConceptChanges,
    ConceptDraft,
)
from app.domain.errors import ConceptValidationError


def draft(**overrides: Any) -> ConceptDraft:
    data: dict[str, Any] = {
        "name": "Ciberseguridad",
        "description": "Ataques informáticos, robo de datos y fraudes digitales",
        "keywords": ("ciberataque", "hackeo", "ransomware", "filtración de datos", "phishing"),
        "exclude_terms": ("curso", "webinar", "diplomado"),
        "color": "#2E86DE",
    }
    data.update(overrides)
    return ConceptDraft.validated(**data)


def problems(**overrides: Any) -> list[dict[str, str]]:
    with pytest.raises(ConceptValidationError) as error:
        draft(**overrides)
    # details es dict[str, object]; ConceptDraft siempre pone aquí esta lista.
    return cast(list[dict[str, str]], error.value.details["problemas"])


def fields(**overrides: Any) -> list[str]:
    return [p["campo"] for p in problems(**overrides)]


def test_el_ejemplo_de_la_especificacion_es_valido() -> None:
    concept = draft()

    assert concept.name == "Ciberseguridad"
    assert concept.keywords[3] == "filtración de datos"
    assert concept.is_active is True


def test_limpia_espacios_descarta_vacios_y_pone_el_color_en_mayusculas() -> None:
    concept = draft(
        name="  Robo   de vehículos ",
        keywords=(" robo de  auto", "", "   "),
        exclude_terms=(" seguro de auto ",),
        color="#9b59b6",
    )

    assert concept.name == "Robo de vehículos"
    assert concept.keywords == ("robo de auto",)
    assert concept.exclude_terms == ("seguro de auto",)
    assert concept.color == "#9B59B6"


def test_name_norm_ignora_mayusculas_y_acentos_pero_conserva_la_enie() -> None:
    assert draft(name="Extorsión").name_norm == draft(name="EXTORSION").name_norm
    assert draft(name="Niñez").name_norm == "NIÑEZ"


@pytest.mark.parametrize("name", ["", "A", "x" * (NAME_MAX_LENGTH + 1)])
def test_nombre_muy_corto_o_muy_largo(name: str) -> None:
    assert fields(name=name) == ["name"]


def test_sin_palabras_clave() -> None:
    assert problems(keywords=("", " ")) == [
        {"campo": "keywords", "mensaje": "Agrega al menos una palabra clave."}
    ]


def test_palabras_repetidas_sin_importar_mayusculas_ni_acentos() -> None:
    [problem] = problems(keywords=("Hackeo", "hackéo", "phishing"))

    assert problem["campo"] == "keywords"
    assert '"hackéo" está repetida' in problem["mensaje"]


def test_exclusion_igual_a_palabra_clave() -> None:
    [problem] = problems(exclude_terms=("Ransomware",))

    assert problem["campo"] == "exclude_terms"
    assert "se anularían" in problem["mensaje"]


@pytest.mark.parametrize(
    ("term", "fragment"),
    [
        ('"hackeo"', "comillas"),
        ("(ataque", "comillas, paréntesis"),
        ("site:gob.mx", "dos puntos"),
        ("-curso", "guion"),
        ("ataque OR robo", '"OR" y "AND"'),
        ("robo and asalto", '"OR" y "AND"'),
        ("x", "entre 2 y 80"),
    ],
)
def test_terminos_que_los_buscadores_tomarian_como_ordenes(term: str, fragment: str) -> None:
    [problem] = problems(keywords=("phishing", term))

    assert problem["campo"] == "keywords"
    assert fragment in problem["mensaje"]


def test_las_exclusiones_tienen_las_mismas_reglas() -> None:
    assert fields(exclude_terms=("curso", "Curso", "-webinar")) == [
        "exclude_terms",
        "exclude_terms",
    ]


def test_demasiadas_palabras_clave() -> None:
    many = tuple(f"palabra{i}" for i in range(MAX_TERMS + 1))

    assert fields(keywords=many) == ["keywords"]


@pytest.mark.parametrize("color", ["2E86DE", "#2E86D", "#GGGGGG", "azul"])
def test_color_invalido(color: str) -> None:
    assert fields(color=color) == ["color"]


def test_descripcion_muy_larga() -> None:
    assert fields(description="x" * 501) == ["description"]


def test_reporta_todos_los_problemas_a_la_vez() -> None:
    assert fields(name="", keywords=(), color="rojo") == ["name", "keywords", "color"]


def test_cambios_parciales_conservan_lo_demas() -> None:
    current = draft()

    updated = ConceptChanges(is_active=False, color="#000000").apply_to(current)

    assert updated.is_active is False
    assert updated.color == "#000000"
    assert updated.keywords == current.keywords
    assert updated.name == current.name


def test_cambios_parciales_validan_el_resultado_completo() -> None:
    # La exclusión nueva choca con una palabra clave que no se tocó.
    with pytest.raises(ConceptValidationError, match="datos inválidos"):
        ConceptChanges(exclude_terms=("phishing",)).apply_to(draft())
