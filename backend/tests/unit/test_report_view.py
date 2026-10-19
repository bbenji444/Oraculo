"""Cifras y gráficas del reporte calculadas de los datos, sin IA (§15)."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from app.adapters.reports.view import (
    MAX_SOURCES,
    MAX_SUBREGION_ROWS,
    build_view,
    day_bars,
    news_groups,
    source_bars,
)
from app.application.ports.reports import SubregionCount
from app.application.use_cases.reports import ReportData, ReportFormat
from tests.unit.application.test_reports_use_case import (
    ACTOR,
    IZTAPALAPA_NOTE,
    STATE_NOTE,
    UNLOCATED_NOTE,
    build,
    item,
    search,
)

pytestmark = pytest.mark.anyio

FROM, TO = date(2026, 10, 10), date(2026, 10, 17)


def at(day: int, hour: int = 18) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


def test_un_dia_por_barra_con_los_dias_sin_notas_en_cero() -> None:
    notes = [replace(item(i), published_at=at(14)) for i in range(3)]
    # 03:00 UTC del 16 es todavía el 15 en la Ciudad de México.
    notes.append(replace(item(9), published_at=at(16, 3)))
    notes.append(replace(item(10), published_at=None))

    bars, unit = day_bars(notes, FROM, TO)

    assert unit == "día"
    assert [b.label for b in bars][:2] == ["10/10", "11/10"]
    assert [(b.label, b.detail, b.count) for b in bars if b.count] == [
        ("14/10", "mié", 3),
        ("15/10", "jue", 1),
    ]
    assert len(bars) == 8
    peak = next(b for b in bars if b.count == 3)
    assert (peak.share, peak.percent) == (1.0, 60)


def test_periodos_largos_por_semana() -> None:
    bars, unit = day_bars([replace(item(1), published_at=at(14))], date(2026, 8, 1), TO)

    assert unit == "semana"
    assert bars[0].label == "01/08"
    assert bars[0].detail == "al 07/08"
    assert sum(b.count for b in bars) == 1


def test_un_medio_cuenta_una_vez_aunque_una_nota_traiga_solo_el_dominio() -> None:
    notes = [
        replace(item(1), source_name="La Silla Rota", source_domain="lasillarota.com"),
        replace(item(2), source_name=None, source_domain="lasillarota.com"),
        replace(item(3), source_name=None, source_domain="infobae.com"),
    ]

    bars = source_bars(notes)

    assert [(b.label, b.count) for b in bars] == [("La Silla Rota", 2), ("infobae.com", 1)]


def test_solo_los_medios_con_mas_notas() -> None:
    notes = [replace(item(i), source_name=None, source_domain=f"m{i}.mx") for i in range(9)]

    assert len(source_bars(notes)) == MAX_SOURCES


def test_grupos_en_orden_y_numeracion_corrida() -> None:
    outside = replace(IZTAPALAPA_NOTE, article_id=7, in_region=False)
    unlocated = replace(UNLOCATED_NOTE, in_region=None)

    groups = news_groups([unlocated, outside, IZTAPALAPA_NOTE, STATE_NOTE], "Jalisco")

    assert [(g.key, g.title) for g in groups] == [
        ("inside", "En Jalisco"),
        ("outside", "Fuera de Jalisco"),
        ("unlocated", "Sin ubicación"),
    ]
    numbers = [(n.number, n.article.article_id) for g in groups for n in g.articles]
    assert numbers == [(1, 1), (2, 2), (3, 7), (4, 3)]


async def report() -> ReportData:
    row = search()
    return await build(row).execute(row.search_id, ReportFormat.PDF, ACTOR)


async def test_datos_clave_de_la_portada() -> None:
    # Conteos coherentes con las 3 notas: 2 en Iztapalapa y 1 fuera.
    data = replace(
        await report(), counts=(SubregionCount("09007", "Iztapalapa", 2),), coarser=0, outside=1
    )

    view = build_view(data)

    assert view.title == "Extorsión"
    assert [(f.label, f.value, f.note) for f in view.facts] == [
        ("Municipio con más notas", "Iztapalapa", "2 notas"),
        # 00:00 UTC del 16 todavía es el jueves 15 en la Ciudad de México.
        ("Día con más notas", "jue 15/10", "3 notas"),
        ("Medio con más notas", "El Universal", "3 notas"),
        ("Dentro de la región", "67 %", "2 de 3 notas"),
    ]
    assert (view.total, view.inside, view.inside_percent) == (3, 2, 67)


async def test_la_tabla_junta_en_otros_lo_que_no_cabe() -> None:
    many = tuple(
        SubregionCount(f"09{i:03d}", f"Alcaldía {i}", 20 - i) for i in range(MAX_SUBREGION_ROWS + 3)
    )

    view = build_view(replace(await report(), counts=many))

    assert len(view.subregions) == MAX_SUBREGION_ROWS
    assert (view.other_subregions, view.level_plural) == (3, "municipios")
    assert view.other_notes == sum(c.count for c in many[MAX_SUBREGION_ROWS:])
