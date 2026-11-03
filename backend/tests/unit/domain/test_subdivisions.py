"""Regla de las subdivisiones: la palabra del tema en el título o el resumen (03/11/2026)."""

from app.domain.subdivisions import TopicMatcher

HOMICIDIO = TopicMatcher(["homicidio", "asesinato", "ataque armado"])


def test_cuenta_en_el_titulo_o_en_el_resumen_sin_importar_acentos() -> None:
    assert HOMICIDIO.found_in("FGR atrae el HOMICIDIO de un periodista", None)
    assert HOMICIDIO.found_in("FGR detiene a «El Chuy»", "Lo acusan del asesinato de un edil.")
    assert HOMICIDIO.found_in("Ataque  armado en Culiacán", None)


def test_caso_real_sin_la_palabra_arriba_no_cuenta() -> None:
    # Índice local, 02/11/2026: «asesinato» solo aparecía en el cuerpo.
    assert not HOMICIDIO.found_in("Brota más corrupción en el INE", None)
    assert not HOMICIDIO.found_in("El Isra ofreció 1 millón de dólares por su liberación", "")


def test_palabras_completas() -> None:
    # «homicidios» es otra palabra: las listas traen el plural aparte.
    assert not HOMICIDIO.found_in("Bajan los homicidios dolosos", None)
    assert not HOMICIDIO.found_in("Ataque armadorizado", None)


def test_sin_subdivision_todo_pasa() -> None:
    assert TopicMatcher([]).found_in("Cualquier nota", None)
    assert TopicMatcher(["  "]).found_in("Cualquier nota", None)
