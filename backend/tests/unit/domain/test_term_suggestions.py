"""Limpieza de las frases que propone la IA (ADR-0109) y el texto literal (ADR-0113)."""

from datetime import date
from typing import cast

import pytest

from app.domain.concept import OPEN_MAX_PHRASES, TERM_MAX_LENGTH, TERM_MIN_LENGTH
from app.domain.errors import ConceptValidationError
from app.domain.queries import CountryFilter, DateWindow, QueryPlace
from app.domain.query_dialects import GOOGLE_MAX_WORDS
from app.domain.term_suggestions import (
    _MAX_TIME_WORDS,
    MAX_SUGGESTED_EXCLUSIONS,
    QUICK_MIN_USEFUL_CHARS,
    EmptySuggestionError,
    clean_suggestion,
    literal_entities,
    literal_fits,
    literal_phrase,
    names_whole_world,
    validated_intent,
    with_literal,
    without_places,
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


# --- El texto literal del analista (ADR-0113) ---------------------------------


def test_literal_phrase_conserva_mayusculas_acentos_y_orden() -> None:
    # Benji, 18/11/2026: buscó «Hacker Eternal» y salió «Hackeo Eternal».
    assert literal_phrase("Hacker Eternal", None) == "Hacker Eternal"
    assert literal_phrase("  hacker   eternal ", None) == "hacker eternal"
    assert literal_phrase("eternal hacker", None) == "eternal hacker"
    assert literal_phrase("extorsión a comerciantes en Iztapalapa", "Iztapalapa") == (
        "extorsión a comerciantes"
    )


def test_literal_phrase_quita_el_lugar_con_su_preposicion() -> None:
    assert literal_phrase("robo de autos en Jalisco", "Jalisco") == "robo de autos"
    assert literal_phrase("Robo de autos en la Ciudad de México", "Ciudad de México") == (
        "Robo de autos"
    )
    # Sin preposición y sin acentos también es el lugar.
    assert literal_phrase("robo de autos jalisco", "Jalisco") == "robo de autos"
    # Por su alias del catálogo («CDMX»), aunque la IA diga el nombre largo.
    assert literal_phrase("robo de autos en la CDMX", "Ciudad de México", aliases=("CDMX",)) == (
        "robo de autos"
    )


def test_no_quita_un_lugar_que_es_parte_de_un_nombre() -> None:
    assert literal_phrase("Cártel de Sinaloa", "Sinaloa") == "Cártel de Sinaloa"
    assert literal_phrase("Universidad de Guadalajara", "Guadalajara") == (
        "Universidad de Guadalajara"
    )
    # En minúsculas lo protege la entidad que reconoció la IA.
    assert literal_phrase(
        "ataques del cártel de Sinaloa", "Sinaloa", entities=("cártel de Sinaloa",)
    ) == ("ataques del cártel de Sinaloa")


def test_literal_phrase_quita_todo_el_mundo() -> None:
    assert literal_phrase("bases de datos hackeadas en todo el mundo", None) == (
        "bases de datos hackeadas"
    )
    assert literal_phrase("Ataques de ransomware a nivel mundial", None) == (
        "Ataques de ransomware"
    )
    # «el Mundial» es el de futbol: se queda.
    assert literal_phrase("boletos para el Mundial", None) == "boletos para el Mundial"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hackeos de hoy", "hackeos"),
        ("robo de autos en Jalisco esta semana", "robo de autos"),
        ("extorsiones en los últimos 7 días", "extorsiones"),
        ("últimos 30 días hacker eternal", "hacker eternal"),
        # «Hoy» al inicio puede ser un nombre: el programa «Hoy No Circula».
        ("Hoy No Circula", "Hoy No Circula"),
    ],
)
def test_literal_phrase_quita_frases_de_tiempo_obvias(text: str, expected: str) -> None:
    assert literal_phrase(text, "Jalisco") == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"hacker eternal"', "hacker eternal"),
        ("«Hacker Eternal»", "Hacker Eternal"),
        ("hacker OR eternal", "hacker eternal"),
        ("hacker eternal -curso", "hacker eternal"),
        ("site:x.com hacker eternal", "hacker eternal"),
        ("(hacker) eternal.", "hacker eternal"),
    ],
)
def test_literal_phrase_quita_comillas_y_operadores(text: str, expected: str) -> None:
    assert literal_phrase(text, None) == expected


# Más de 32 palabras (el tope de Google, hallazgo 7 de la revisión del
# 18/11/2026) no cabe; antes el tope era de 80 caracteres.
@pytest.mark.parametrize(
    "text", ["en todo el mundo", "en Jalisco", "x", "palabra " * (GOOGLE_MAX_WORDS + 1)]
)
def test_literal_phrase_vacio_o_que_no_se_puede_buscar_es_none(text: str) -> None:
    assert literal_phrase(text, "Jalisco") is None


def test_names_whole_world_vive_en_el_dominio() -> None:
    assert names_whole_world("secuestros en todos los países")
    assert not names_whole_world("boletos para el Mundial")


def test_with_literal_va_primero_sin_repetir_y_respeta_el_tope_de_12() -> None:
    phrases = ["hackeo Eternal", "Hacker Eternal", *(f"Eternal frase {i}" for i in range(20))]

    keywords, _ = with_literal("hacker eternal", phrases, [])

    assert keywords[0] == "hacker eternal"
    assert keywords[1] == "hackeo Eternal"
    # «Hacker Eternal» es el literal con otras mayúsculas: no se repite.
    assert "Hacker Eternal" not in keywords
    assert len(keywords) == OPEN_MAX_PHRASES


def test_with_literal_sin_literal_deja_las_frases_de_la_ia() -> None:
    assert with_literal(None, ["filtran datos"], ["curso"]) == (("filtran datos",), ("curso",))


def test_exclusion_igual_al_literal_o_dentro_de_el_se_quita() -> None:
    _, exclusions = with_literal(
        "curso de hacker eternal",
        ["Eternal filtra"],
        ["Curso de hacker eternal", "curso", "taller"],
    )

    assert exclusions == ("taller",)


def test_entidad_que_no_esta_en_el_texto_se_descarta() -> None:
    # La IA «corrige» hacker a hackeo: no es lo que escribió la persona.
    assert literal_entities("hacker eternal", ["Hackeo Eternal", "Hackeo"]) == ()
    # La que sí está vuelve con la grafía de la persona, no la de la IA.
    assert literal_entities("hacker eternal", ["Eternal", "ETERNAL"]) == ("eternal",)
    assert literal_entities("Ataque de LockBit a Pemex", ["lockbit", "PEMEX", "Pémex"]) == (
        "LockBit",
        "Pemex",
    )
    # Tienen que estar juntas y en orden, como palabras completas.
    assert literal_entities("eternal hacker", ["hacker eternal", "Eter"]) == ()


def test_frases_sin_la_entidad_se_descartan() -> None:
    result = clean_suggestion(
        "Hackeo Eternal",
        ["hackean sistemas", "Eternal filtra datos", "hackeo eternal", "roban datos"],
        [],
        entities=("eternal",),
    )

    assert result.phrases == ("Eternal filtra datos", "hackeo eternal")
    assert result.entities == ("eternal",)


def test_sin_entidades_no_se_filtra_ninguna_frase() -> None:
    result = clean_suggestion("Robo", ["roban autos", "asaltan conductores"], [])

    assert result.phrases == ("roban autos", "asaltan conductores")
    assert result.entities == ()


def test_si_ninguna_frase_lleva_la_entidad_la_busqueda_rapida_puede_seguir() -> None:
    # El formulario necesita al menos una frase; la búsqueda rápida tiene el literal.
    with pytest.raises(EmptySuggestionError):
        clean_suggestion("x", ["hackean sistemas"], [], entities=("eternal",))

    result = clean_suggestion(
        "x", ["hackean sistemas"], [], entities=("eternal",), require_phrases=False
    )

    assert result.phrases == ()


def test_un_lugar_no_es_entidad() -> None:
    # Revisión del 18/11/2026 (hallazgo 3): la IA puso «Jalisco» en entities;
    # se exigía en cada frase y en cada nota («Debe hablar de: Jalisco»).
    entities = ("Jalisco", "CJNG", "Cártel de Sinaloa")

    kept = without_places(entities, ["jalisco", "México", "", "Sinaloa"])

    # «Cártel de Sinaloa» es un nombre propio que lleva un lugar: se queda.
    assert kept == ("CJNG", "Cártel de Sinaloa")
    assert without_places(entities, []) == entities


def test_la_frase_de_tiempo_mas_larga_se_quita_completa() -> None:
    # Revisión del 18/11/2026 (hallazgo 8): el tope de palabras de una frase
    # de tiempo es el de la más larga que reconoce el patrón (5).
    assert literal_phrase("fraudes durante las últimas 24 horas", None) == "fraudes"
    longest = ["durante", "las", "últimas", "24", "horas"]
    assert len(longest) == _MAX_TIME_WORDS


def test_el_ejemplo_de_clean_suggestion_es_su_repr_real() -> None:
    # El Example del docstring (hallazgo 8) no mostraba el campo entities.
    result = clean_suggestion("Hackeos", ["filtran datos", "Filtran datos", "a OR b"], ["curso"])

    assert repr(result) == (
        "SuggestedTerms(name='Hackeos', phrases=('filtran datos',), "
        "exclude_terms=('curso',), entities=())"
    )


# --- Revisión del 18/11/2026 (hallazgo 7): el literal casi siempre sale ---


@pytest.mark.parametrize("text", ["Pemex", "LockBit", "IA", "huachicol", " Eternal "])
def test_la_busqueda_rapida_acepta_un_nombre_solo(text: str) -> None:
    assert validated_intent(text, quick=True) == text.strip()


@pytest.mark.parametrize("text", ["", "x", " . ", "¿?", "x" * 501])
def test_la_busqueda_rapida_pide_dos_letras_o_numeros(text: str) -> None:
    with pytest.raises(ConceptValidationError) as error:
        validated_intent(text, quick=True)

    problems = cast(list[dict[str, str]], error.value.details["problemas"])
    assert [p["campo"] for p in problems] == ["description"]
    assert QUICK_MIN_USEFUL_CHARS == TERM_MIN_LENGTH


def test_el_formulario_sigue_pidiendo_una_descripcion() -> None:
    # La propuesta de frases del formulario necesita contexto para la IA.
    with pytest.raises(ConceptValidationError):
        validated_intent("Pemex")


LONG_TEXT = (
    "ataques de hackers a la Secretaría de la Defensa Nacional y a otras dependencias "
    "del gobierno federal mexicano"
)


def test_un_texto_de_mas_de_80_caracteres_tambien_es_literal() -> None:
    assert len(LONG_TEXT) > TERM_MAX_LENGTH
    assert literal_phrase(LONG_TEXT, None) == LONG_TEXT


def test_el_literal_tiene_el_tope_de_palabras_de_google() -> None:
    words = [f"palabra{i}" for i in range(GOOGLE_MAX_WORDS + 1)]

    assert literal_phrase(" ".join(words[:GOOGLE_MAX_WORDS]), None) is not None
    assert literal_phrase(" ".join(words), None) is None


def test_el_literal_debe_caber_con_el_lugar_y_las_fechas() -> None:
    jalisco = QueryPlace(("Jalisco",), (), CountryFilter("México", "MX", "MX", "Mexico"))
    week = DateWindow.last_days(7, date(2026, 11, 18))
    short = "robo de autos con violencia"
    longest = " ".join(f"palabra{i}" for i in range(GOOGLE_MAX_WORDS))

    assert literal_fits(short, jalisco, ("curso",), week)
    assert literal_fits(LONG_TEXT, jalisco, ("curso",), week)
    # 32 palabras más el lugar y «when:7d» pasan del límite de Google.
    assert not literal_fits(longest, jalisco, (), week)
