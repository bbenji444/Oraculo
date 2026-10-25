"""Nota del índice local: validación, texto de búsqueda y reglas de GDELT."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from app.domain.news_index import (
    BODY_SEPARATOR,
    MAX_BODY_PHRASES,
    GdeltLocation,
    InvalidNewsError,
    MexicoMentions,
    NewsItem,
    body_terms_from,
    inegi_states,
    keep_gdelt_note,
)

MEXICO_TZ = timezone(timedelta(hours=-6))
CDMX = GdeltLocation(4, "Mexico City, Distrito Federal, Mexico", "MX", "MX09", 19.4, -99.1)
COUNTRY = GdeltLocation(1, "Mexico", "MX", "MX", 23.0, -102.0)
MADRID = GdeltLocation(4, "Madrid, Madrid, Spain", "SP", "SP29", 40.4, -3.7)


def item(**overrides: Any) -> NewsItem:
    data: dict[str, Any] = {
        "source": "rss:la-jornada",
        "url": "https://www.jornada.com.mx/noticia/2026/10/16/peñon",
        "title": "  Hackeo   en el Peñón ",
        "published_at": datetime(2026, 10, 16, 8, 0, tzinfo=MEXICO_TZ),
        "snippet": "Ataque informático a una dependencia",
    }
    data.update(overrides)
    return NewsItem.create(**data)


def test_limpia_y_normaliza_conservando_la_enie() -> None:
    news = item()

    assert news.title == "Hackeo en el Peñón"
    assert news.text_norm == "HACKEO EN EL PEÑON ATAQUE INFORMATICO A UNA DEPENDENCIA"
    assert news.source_domain == "jornada.com.mx"
    assert news.published_at == datetime(2026, 10, 16, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"url": "ftp://x"}, "URL"),
        ({"title": "  "}, "título"),
        ({"published_at": None}, "fecha"),
        ({"published_at": datetime(2026, 10, 16)}, "fecha"),  # noqa: DTZ001 — se prueba justo la fecha sin zona
    ],
)
def test_notas_inutilizables_se_rechazan(overrides: dict[str, Any], fragment: str) -> None:
    with pytest.raises(InvalidNewsError, match=fragment):
        item(**overrides)


def test_solo_espanol_con_alguna_ubicacion_en_mexico() -> None:
    assert keep_gdelt_note("spa", [MADRID, CDMX]) is True
    assert keep_gdelt_note("spa", [MADRID]) is False
    assert keep_gdelt_note("por", [CDMX]) is False
    assert keep_gdelt_note(None, [CDMX]) is False


def test_estados_inegi_sin_repetir_y_sin_el_nivel_pais() -> None:
    fips = {"MX09": "09", "MX07": "05"}
    coahuila = GdeltLocation(4, "Saltillo", "MX", "MX07", None, None)

    assert inegi_states([COUNTRY, CDMX, coahuila, CDMX, MADRID], fips) == ("09", "05")


def test_ubicaciones_repetidas_se_guardan_una_vez() -> None:
    # GDELT repite la ubicación por cada mención: en el GKG del 16/10/2026 una
    # nota del huracán Trudy traía "Mexico" 10 veces y la misma ciudad 5.
    news = item(gdelt_locations=[COUNTRY, CDMX, COUNTRY, CDMX, COUNTRY])

    assert news.gdelt_locations == (COUNTRY, CDMX)


# --- Ngramas (ADR-0014) ---


def test_frases_del_cuerpo_normalizadas_sin_repetir_y_con_tope() -> None:
    assert body_terms_from(["Robo en  Peñón", "robo en peñón", " ", "de los Baños"]) == (
        "ROBO EN PEÑON | DE LOS BAÑOS"
    )
    assert body_terms_from([]) is None
    many = body_terms_from(f"frase {n}" for n in range(MAX_BODY_PHRASES + 50))
    assert many is not None
    assert len(many.split(BODY_SEPARATOR)) == MAX_BODY_PHRASES


def test_la_nota_guarda_su_cuerpo_aparte_del_texto_que_se_muestra() -> None:
    news = item(body_phrases=["detienen en Iztapalapa a", "en Iztapalapa a un"])

    assert news.body_terms == "DETIENEN EN IZTAPALAPA A | EN IZTAPALAPA A UN"
    assert "IZTAPALAPA" not in news.text_norm


MENTIONS = MexicoMentions(
    ["Ciudad de México", "CDMX", "Nuevo León", "Baja California", "Baja California Sur"]
)


@pytest.mark.parametrize(
    ("text", "domain", "expected"),
    [
        ("ROBO EN UN BANCO DE NUEVO LEON", None, True),
        ("EL GOBIERNO MEXICANO ANUNCIO", None, True),
        ("CORTE DE LUZ EN LA CDMX", None, True),
        ("BAJA CALIFORNIA SUR SIN AGUA", None, True),
        # "LEON" solo (Guanajuato o España) no basta: el término es completo.
        ("SUBE EL PRECIO EN LEON", None, False),
        ("ROBOS EN CARTAGENA", None, False),
        # "MEXICOS" no es "MEXICO": se compara la palabra completa.
        ("LOS MEXICOSAURIOS", None, False),
        ("ROBOS EN CARTAGENA", "vanguardia.com.mx", True),
    ],
)
def test_reconoce_si_una_nota_menciona_mexico(
    text: str, domain: str | None, expected: bool
) -> None:
    assert MENTIONS.found_in(text, domain) is expected


def test_repara_el_mojibake_de_gdelt_al_entrar() -> None:
    # Título real de tiempo.com.mx tal como lo trae GDELT (F12.1).
    note = item(title="Maru seÃ±alÃ³ corrupciÃ³n ðŸŽ¦", snippet="JÃ¡uregui", source_name="Ã‰xito")

    assert note.title == "Maru señaló corrupción 🎦"
    assert note.snippet == "Jáuregui"
    assert note.source_name == "Éxito"
    assert note.text_norm == "MARU SEÑALO CORRUPCION 🎦 JAUREGUI"
