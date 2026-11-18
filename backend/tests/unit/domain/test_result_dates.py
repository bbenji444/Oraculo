"""Fechas en texto de Google web y notas sin fecha en el periodo (ADR-0115)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.queries import Provider
from app.domain.result_dates import kept_by_window, parse_result_date
from app.domain.schedule import RunWindow

MEXICO_CITY = ZoneInfo("America/Mexico_City")
NOW = datetime(2026, 11, 18, 19, 3, tzinfo=UTC)
# Mediodía de la Ciudad de México (UTC-6) en UTC.
NOON = 18


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hace 15 horas", NOW - timedelta(hours=15)),
        ("hace 5 días", NOW - timedelta(days=5)),
        ("hace 1 día", NOW - timedelta(days=1)),
        ("hace un día", NOW - timedelta(days=1)),
        ("hace 30 minutos", NOW - timedelta(minutes=30)),
        ("hace 2 semanas", NOW - timedelta(weeks=2)),
        ("Hace 3 Horas", NOW - timedelta(hours=3)),
        ("ayer", NOW - timedelta(days=1)),
        ("hoy", NOW),
        ("21h ago", NOW - timedelta(hours=21)),
        ("2 days ago", NOW - timedelta(days=2)),
        ("an hour ago", NOW - timedelta(hours=1)),
        ("17 nov 2026", datetime(2026, 11, 17, NOON, tzinfo=UTC)),
        ("17 de nov. de 2026", datetime(2026, 11, 17, NOON, tzinfo=UTC)),
        ("17 de noviembre de 2026", datetime(2026, 11, 17, NOON, tzinfo=UTC)),
        ("3 sept 2026", datetime(2026, 9, 3, NOON, tzinfo=UTC)),
        ("Nov 30, 2022", datetime(2022, 11, 30, NOON, tzinfo=UTC)),
    ],
)
def test_entiende_los_formatos_de_google(text: str, expected: datetime) -> None:
    assert parse_result_date(text, NOW, MEXICO_CITY) == expected


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "Más de 1 k vistas",
        "hace muchos días",
        "hace 3 lustros",
        "31 feb 2026",
        "17 foo 2026",
        # Una fecha en el futuro no es una publicación: no se inventa.
        "25 dic 2026",
    ],
)
def test_lo_que_no_entiende_queda_sin_fecha(text: str | None) -> None:
    assert parse_result_date(text, NOW, MEXICO_CITY) is None


# Revisión del 18/11/2026 (hallazgo 5): «hace 3 meses» o «2 years ago» quedaban
# sin fecha y una nota que Google mismo marca como vieja se colaba a la ventana
# estricta de una búsqueda manual. Mes = 30 días y año = 365: es aproximado,
# pero basta para saber que no es de esta semana.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hace 1 mes", NOW - timedelta(days=30)),
        ("hace un mes", NOW - timedelta(days=30)),
        ("hace 3 meses", NOW - timedelta(days=90)),
        ("hace 1 año", NOW - timedelta(days=365)),
        ("hace 2 años", NOW - timedelta(days=730)),
        ("Hace 2 AÑOS", NOW - timedelta(days=730)),
        ("3 months ago", NOW - timedelta(days=90)),
        ("a month ago", NOW - timedelta(days=30)),
        ("2 years ago", NOW - timedelta(days=730)),
        ("a year ago", NOW - timedelta(days=365)),
    ],
)
def test_entiende_meses_y_anos(text: str, expected: datetime) -> None:
    assert parse_result_date(text, NOW, MEXICO_CITY) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Sin año es del año en curso...
        ("17 nov", datetime(2026, 11, 17, NOON, tzinfo=UTC)),
        ("17 de nov.", datetime(2026, 11, 17, NOON, tzinfo=UTC)),
        ("3 de septiembre", datetime(2026, 9, 3, NOON, tzinfo=UTC)),
        ("Nov 17", datetime(2026, 11, 17, NOON, tzinfo=UTC)),
        ("Mar 5", datetime(2026, 3, 5, NOON, tzinfo=UTC)),
        # ... salvo que quede en el futuro: entonces es del año pasado.
        ("25 dic", datetime(2025, 12, 25, NOON, tzinfo=UTC)),
        ("Dec 25", datetime(2025, 12, 25, NOON, tzinfo=UTC)),
    ],
)
def test_una_fecha_sin_ano_es_del_ano_en_curso_o_del_anterior(
    text: str, expected: datetime
) -> None:
    assert parse_result_date(text, NOW, MEXICO_CITY) == expected


def test_una_fecha_sin_ano_que_no_existe_queda_sin_fecha() -> None:
    # 2026 no es bisiesto: «29 feb» no se inventa con otro día.
    assert parse_result_date("29 feb", NOW, MEXICO_CITY) is None


def test_lo_que_google_marca_como_viejo_sale_de_la_ventana_de_la_semana() -> None:
    old = parse_result_date("hace 3 meses", NOW, MEXICO_CITY)

    assert not kept_by_window(WINDOW, old, (Provider.SEARCHAPI_WEB,), manual=True)


WINDOW = RunWindow(NOW - timedelta(days=7), NOW)


def test_con_fecha_manda_la_ventana_para_todos() -> None:
    inside, outside = NOW - timedelta(days=1), NOW - timedelta(days=9)

    assert kept_by_window(WINDOW, inside, (Provider.GOOGLE_NEWS_RSS,), manual=True)
    assert not kept_by_window(WINDOW, outside, (Provider.SEARCHAPI_WEB,), manual=True)


def test_sin_fecha_solo_se_queda_lo_de_google_web_en_las_manuales() -> None:
    assert kept_by_window(WINDOW, None, (Provider.SEARCHAPI_WEB,), manual=True)
    assert kept_by_window(WINDOW, None, ("google_news_rss", "searchapi_web"), manual=True)
    assert not kept_by_window(WINDOW, None, (Provider.GOOGLE_NEWS_RSS,), manual=True)
    assert not kept_by_window(WINDOW, None, (Provider.SEARCHAPI,), manual=True)
    # En las corridas automáticas una nota sin fecha nunca se queda.
    assert not kept_by_window(WINDOW, None, (Provider.SEARCHAPI_WEB,), manual=False)
