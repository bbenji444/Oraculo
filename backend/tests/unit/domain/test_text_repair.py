"""Reparación de Mojibake (F12.1).

Los casos «reales» son títulos tal como están en la base del 24/10/2026,
con el Mojibake que trajo GDELT de tiempo.com.mx y puentelibre.mx.
"""

import pytest

from app.domain.text_repair import clean_text, repair_mojibake


@pytest.mark.parametrize(
    ("broken", "expected"),
    [
        (
            "Maru seÃ±alÃ³ corrupciÃ³n de su exfiscal ante la FGR, revela Godoy ðŸŽ¦",
            "Maru señaló corrupción de su exfiscal ante la FGR, revela Godoy 🎦",
        ),
        (
            "Â¿QuÃ© es el virus shamonda y cÃ³mo se contagia?ðŸŽ¦",
            "¿Qué es el virus shamonda y cómo se contagia?🎦",
        ),
        (
            '"Liberen a JÃ¡uregui", exige caravana con cientos de carros en ChihuahuaðŸŽ¦',
            '"Liberen a Jáuregui", exige caravana con cientos de carros en Chihuahua🎦',
        ),
    ],
)
def test_repara_titulos_reales(broken: str, expected: str) -> None:
    assert repair_mojibake(broken) == expected


@pytest.mark.parametrize(
    "correct",
    [
        "Peñón de los Baños",
        "¿Qué pasó en Ecatepec? Está bien",
        # Mayúscula acentuada seguida de comilla tipográfica: parece el inicio
        # de una secuencia rota, pero el resultado sería cirílico y se deja.
        "«ADIÓS”» MÉXICO",
        "Costó 50 € — según la FGR",
        "São Paulo",
        "",
    ],
)
def test_no_toca_texto_correcto(correct: str) -> None:
    assert repair_mojibake(correct) == correct


def test_comillas_y_guiones_tipograficos() -> None:
    # 0x9D no existe en Windows-1252; los lectores tolerantes lo dejan como
    # el carácter de control U+009D.
    assert repair_mojibake("â€œComillasâ€\x9d y guiÃ³n â€” largo") == "“Comillas” y guión — largo"


@pytest.mark.parametrize(
    ("broken", "expected"),
    [
        # Casos reales de hoytamaulipas.net: GDELT cambió “ por " y se perdió
        # el byte que formaba la letra o el emoji.
        (
            'Hoy Tamaulipas - Ã"rdenes de aprehension llevan hasta ocho anios',
            "Hoy Tamaulipas - Órdenes de aprehension llevan hasta ocho anios",
        ),
        (
            'Encontraron pez remo en playa al norte de Chile ðŸ"¸',
            "Encontraron pez remo en playa al norte de Chile 📸",
        ),
        # «…» del medio en Windows-1252, leído como Latin-1 y luego roto.
        ("La falsedad de Romulo PerezÂ…", "La falsedad de Romulo Perez…"),
        ("La falsedad de Romulo PerezÂ\x85", "La falsedad de Romulo Perez…"),
    ],
)
def test_comillas_rectas_y_doble_error(broken: str, expected: str) -> None:
    assert repair_mojibake(broken) == expected


def test_comilla_recta_legitima_no_cambia() -> None:
    assert repair_mojibake('Dijo "MÉXICO" y "café"') == 'Dijo "MÉXICO" y "café"'


def test_repara_solo_la_parte_rota() -> None:
    assert repair_mojibake("bien: niño, mal: niÃ±o") == "bien: niño, mal: niño"


def test_mojibake_doble() -> None:
    assert repair_mojibake("SÃƒÂ©ptimo") == "Séptimo"


def test_secuencia_incompleta_al_final_se_deja() -> None:
    assert repair_mojibake("termina en Ã") == "termina en Ã"


def test_clean_text_junta_espacios_y_repara() -> None:
    assert clean_text("  JÃ¡uregui   en\nChihuahua ") == "Jáuregui en Chihuahua"


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_clean_text_vacio_es_none(empty: str | None) -> None:
    assert clean_text(empty) is None
