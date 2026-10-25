"""Historias (F12.1c, ADR-0026), con títulos reales del 23 y 24/10/2026."""

from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.text.similarity import title_similarity, title_token_similarity
from app.domain.stories import StoryNote, assign_stories, story_tokens, strip_outlet

T0 = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)
IZTAPALAPA = "09007"


def note(
    article_id: int,
    title: str,
    hours: float = 0,
    *,
    place: str | None = None,
    source: str | None = None,
    story_id: int | None = None,
) -> StoryNote:
    return StoryNote(
        article_id=article_id,
        title=title,
        source_name=source,
        source_domain=None,
        published_at=T0 + timedelta(hours=hours),
        place_code=place,
        story_id=story_id,
    )


def group(existing: list[StoryNote], new: list[StoryNote]) -> dict[int, int]:
    return assign_stories(existing, new, title_similarity, title_token_similarity)


@pytest.mark.parametrize(
    ("title", "source", "expected"),
    [
        (
            "Desfile de Día de Muertos en CDMX - Quadratín México",
            "Quadratín México",
            "Desfile de Día de Muertos en CDMX",
        ),
        (
            "Vuelca autobús con integrantes de la GN en Campeche – Periódico Zócalo"
            " | Noticias de Saltillo",
            "Periódico Zócalo",
            "Vuelca autobús con integrantes de la GN en Campeche",
        ),
        # Un guion que no nombra al medio se queda.
        (
            "Sheinbaum - Maru Campos: reunión tensa",
            "Milenio",
            "Sheinbaum - Maru Campos: reunión tensa",
        ),
        ("Sin separadores", None, "Sin separadores"),
    ],
)
def test_quita_el_nombre_del_medio(title: str, source: str | None, expected: str) -> None:
    assert strip_outlet(title, source, None) == expected


def test_palabras_que_distinguen_un_hecho() -> None:
    assert story_tokens("BALACERA EN IZTAPALAPA DEJA DOS MUERTOS HOY") == {
        "BALACERA",
        "IZTAPALAPA",
        "DEJA",
        "MUERTOS",
    }


def test_la_misma_balacera_contada_por_cuatro_medios_es_una_historia() -> None:
    notes = [
        note(
            1,
            "Dos Muertos por Ataque con Arma de Fuego en Ermita Iztapalapa, CDMX",
            0,
            place=IZTAPALAPA,
        ),
        note(
            2,
            "Balacera en Iztapalapa, CDMX, Deja 2 Muertos y Un Herido; Hay 2 Detenidos",
            3,
            place=IZTAPALAPA,
        ),
        note(
            3, "Ataque armado deja dos muertos y un herido en Iztapalapa, CDMX", 5, place=IZTAPALAPA
        ),
        note(
            4,
            "Dos muertos y una persona herida por balacera en Avenida Ermita Iztapalapa",
            9,
            place=IZTAPALAPA,
        ),
    ]

    assert group([], notes) == {1: 1, 2: 1, 3: 1, 4: 1}


def test_palabras_poco_comunes_juntan_sin_lugar() -> None:
    notes = [
        note(
            10,
            "Giran orden de aprehensión contra Eduardo 'N' por asesinato del estilista"
            " Micky Hair en Polanco",
        ),
        note(
            11,
            "Micky Hair: orden de aprehensión contra Eduardo N – Publimetro México",
            4,
            source="Publimetro",
        ),
    ]

    assert group([], notes) == {10: 10, 11: 10}


def test_temas_parecidos_pero_hechos_distintos_no_se_juntan() -> None:
    notes = [
        note(20, "Día de Muertos 2026 en CDMX: calendario de desfiles y ofrendas"),
        note(
            21,
            "Receta de pollo con salsa de cempasúchil: ideal para esta temporada de Día de Muertos",
            2,
        ),
        note(22, "Manifestaciones y frío dominarán este martes en CDMX", 3),
    ]

    assert group([], notes) == {}


def test_se_compara_con_la_primera_nota_no_en_cadena() -> None:
    # 31 se parece a 30 y 32 se parece a 31, pero 32 no se parece a 30: no
    # se arrastra (así se evitaban los grupos de 61 notas).
    notes = [
        note(30, "Balacera en Iztapalapa deja dos muertos y un herido", 0),
        note(31, "Balacera en Iztapalapa deja dos muertos; detienen a dos jóvenes", 1),
        note(32, "Detienen a dos jóvenes motosicarios en la Ciudad de México", 2),
    ]

    assert group([], notes) == {30: 30, 31: 30}


@pytest.mark.parametrize(
    ("hours", "joins"),
    [(47, True), (49, False)],
)
def test_ventana_de_dos_dias_desde_la_ultima_nota(hours: float, joins: bool) -> None:
    first = note(40, "Balacera en Iztapalapa deja dos muertos y un herido", 0)
    later = note(41, "Balacera en Iztapalapa deja dos muertos y un herido hoy", hours)

    assert (group([], [first, later]) == {40: 40, 41: 40}) is joins


def test_la_historia_no_crece_mas_de_tres_dias_desde_la_primera() -> None:
    title = "Balacera en Iztapalapa deja dos muertos y un herido"
    notes = [note(50, title, 0), note(51, title, 40), note(52, title, 75)]

    # 52 está a 35 h de la última (cabe en 2 días) pero a 75 h de la primera.
    assert group([], notes) == {50: 50, 51: 50}


def test_una_nota_nueva_entra_a_una_historia_ya_guardada() -> None:
    existing = [
        note(60, "Balacera en Iztapalapa deja dos muertos y un herido", 0, story_id=60),
        note(61, "Balacera en Iztapalapa deja dos muertos; hay dos detenidos", 2, story_id=60),
    ]
    new = [note(62, "Balacera en Iztapalapa deja dos muertos y un herido en Ermita", 6)]

    assert group(existing, new) == {62: 60}


def test_una_nota_sola_guardada_pasa_a_encabezar_su_historia() -> None:
    existing = [note(70, "Cierran panteón de Janitzio a turistas durante Día de Muertos", 0)]
    new = [
        note(
            71,
            "¿Viajas a Janitzio por el Día de Muertos 2026? Por esta razón cerrarán"
            " el panteón a turistas",
            5,
        )
    ]

    assert group(existing, new) == {70: 70, 71: 70}


def test_clave_de_pais_no_cuenta_como_mismo_lugar() -> None:
    notes = [
        note(
            80,
            "Presidente del Comité de la ONU pide a México dar cuentas sobre localizados",
            0,
            place="MEX",
        ),
        note(
            81,
            "Sheinbaum destaca reconocimiento del Comité de la ONU tras localizar a 16 mil",
            2,
            place="MEX",
        ),
    ]

    assert group([], notes) == {}
