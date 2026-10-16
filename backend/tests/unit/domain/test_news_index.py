"""Nota del índice local: validación, texto de búsqueda y reglas de GDELT."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from app.domain.news_index import (
    GdeltLocation,
    InvalidNewsError,
    NewsItem,
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
