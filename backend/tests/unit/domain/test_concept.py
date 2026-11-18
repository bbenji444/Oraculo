"""Reglas de un concepto: limpieza, validación y cambios parciales."""

from typing import Any, cast

import pytest

from app.domain.concept import (
    MAX_REQUIRED_TERMS,
    MAX_TERMS,
    NAME_MAX_LENGTH,
    OPEN_MAX_PHRASES,
    REQUIRED_FIELD,
    ConceptChanges,
    ConceptDraft,
    QueryMode,
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


# --- Modo abierto (ADR-0109): frases tipo titular, una búsqueda por frase ---


def test_sin_decir_el_modo_el_concepto_es_exacto() -> None:
    # Los conceptos de antes (FGR, temas) no cambian de comportamiento.
    assert draft().query_mode is QueryMode.EXACT


def test_modo_abierto_se_guarda_en_el_borrador() -> None:
    concept = draft(query_mode=QueryMode.OPEN, keywords=("roban auto", "filtran datos"))

    assert concept.query_mode is QueryMode.OPEN
    assert concept.keywords == ("roban auto", "filtran datos")


def test_modo_abierto_admite_hasta_doce_frases() -> None:
    phrases = tuple(f"frase {i}" for i in range(OPEN_MAX_PHRASES))

    assert draft(query_mode=QueryMode.OPEN, keywords=phrases).keywords == phrases


def test_modo_abierto_con_mas_de_doce_frases_es_error_claro() -> None:
    phrases = tuple(f"frase {i}" for i in range(OPEN_MAX_PHRASES + 1))

    found = problems(query_mode=QueryMode.OPEN, keywords=phrases)

    assert [p["campo"] for p in found] == ["keywords"]
    assert "cada frase es una búsqueda" in found[0]["mensaje"]


def test_modo_exacto_sigue_admitiendo_mas_de_doce_palabras() -> None:
    words = tuple(f"palabra{i}" for i in range(OPEN_MAX_PHRASES + 1))

    assert draft(keywords=words).query_mode is QueryMode.EXACT


def test_cambiar_el_modo_vuelve_a_validar_las_frases() -> None:
    words = tuple(f"palabra{i}" for i in range(OPEN_MAX_PHRASES + 1))

    with pytest.raises(ConceptValidationError, match="datos inválidos"):
        ConceptChanges(query_mode=QueryMode.OPEN).apply_to(draft(keywords=words))


def test_cambios_parciales_conservan_el_modo() -> None:
    current = draft(query_mode=QueryMode.OPEN)

    assert ConceptChanges(color="#000000").apply_to(current).query_mode is QueryMode.OPEN


# --- Términos obligatorios de la búsqueda rápida (ADR-0113) ---


def test_sin_terminos_obligatorios_el_concepto_no_cambia() -> None:
    assert draft().required_terms == ()


def test_terminos_obligatorios_se_limpian_y_validan() -> None:
    assert draft(required_terms=(" Eternal ", "")).required_terms == ("Eternal",)
    assert fields(required_terms=("Eternal", "eternal")) == [REQUIRED_FIELD]
    assert fields(required_terms=('"Eternal"',)) == [REQUIRED_FIELD]
    too_many = tuple(f"nombre {i}" for i in range(MAX_REQUIRED_TERMS + 1))
    assert fields(required_terms=too_many) == [REQUIRED_FIELD]


def test_editar_desde_el_formulario_no_borra_los_terminos_obligatorios() -> None:
    current = draft(required_terms=("Eternal",), query_mode=QueryMode.OPEN)

    edited = ConceptChanges(name="hacker eternal", keywords=("hacker eternal",)).apply_to(current)

    assert edited.required_terms == ("Eternal",)


# Revisión del 18/11/2026 (hallazgo 7): el literal de la búsqueda rápida se
# busca completo aunque pase de 80 caracteres; el formulario no cambia.
LONG_LITERAL = (
    "ataques de hackers a la Secretaría de la Defensa Nacional y a otras dependencias "
    "del gobierno federal mexicano"
)


def test_el_literal_de_la_busqueda_rapida_puede_pasar_de_80_caracteres() -> None:
    quick = draft(
        keywords=(LONG_LITERAL, "hackean Sedena"),
        query_mode=QueryMode.OPEN,
        literal_max_words=32,
    )

    assert quick.keywords[0] == LONG_LITERAL


def test_solo_el_literal_tiene_tope_de_palabras() -> None:
    # La segunda frase y el formulario siguen con el tope de 80 caracteres.
    assert fields(
        keywords=("hackean Sedena", LONG_LITERAL), query_mode=QueryMode.OPEN, literal_max_words=32
    ) == ["keywords"]
    assert fields(keywords=(LONG_LITERAL,), query_mode=QueryMode.OPEN) == ["keywords"]
    words = " ".join(f"palabra{i}" for i in range(33))
    assert fields(keywords=(words,), query_mode=QueryMode.OPEN, literal_max_words=32) == [
        "keywords"
    ]
