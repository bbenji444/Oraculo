"""Secciones del reporte Oráculo (F12.10, ADR-0033): sin base, sin IA, sin red."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.adapters.reports.oraculo import (
    NO_CATEGORY,
    NO_STATE,
    OTHER_COLOR,
    badges,
    build_oraculo,
    category_cards,
    clean,
    confidence,
    expediente,
    network_svg,
    state_groups,
    state_stacks,
    timeline,
)
from app.application.ports.search_reads import ArticleItem, CategoryView, JudgementView
from app.domain.authority import Authority
from tests.unit.application.test_reports_use_case import item, place, search

ARMAS = CategoryView(6, "Armas y explosivos")
OTROS = CategoryView(14, "Otros")


def note(
    article_id: int,
    code: str | None,
    category: CategoryView | None,
    published: datetime,
    **extra: Any,
) -> ArticleItem:
    base = item(article_id, primary=place(code, "municipality", "Lugar") if code else None)
    return replace(base, category=category, published_at=published, **extra)


AT_15 = datetime(2026, 10, 25, 21, 10, tzinfo=UTC)  # 15:10 CDMX
NOTES = (
    note(1, "08019", ARMAS, AT_15, category_raw="tráfico de armas", authority=Authority.FGR),
    note(2, "08037", OTROS, AT_15.replace(minute=40), category_raw="Traición a la patria"),
    note(
        3,
        "19039",
        ARMAS,
        datetime(2026, 10, 25, 23, 5, tzinfo=UTC),
        category_raw="tráfico de armas",
    ),
    note(4, None, None, datetime(2026, 10, 26, 2, 0, tzinfo=UTC)),
)


def test_quita_emojis_y_simbolos_que_la_fuente_no_tiene() -> None:
    assert clean("¡Llegaron a la FGR! 👉 Local") == "¡Llegaron a la FGR! Local"
    assert clean("Chihuahua🎦") == "Chihuahua"
    assert clean("Peñón «N» – 3 %") == "Peñón «N» – 3 %"
    assert clean(None) == ""


def test_el_expediente_de_una_corrida_lleva_su_hora_programada() -> None:
    manual = search()
    automatic = replace(manual, scheduled_for=datetime(2026, 10, 26, 5, 0, tzinfo=UTC))

    assert expediente(manual) == "EXP-20261017-1400"
    assert expediente(automatic) == "EXP-FGR-20261025-2300"


def test_tarjetas_por_categoria_con_su_estado_y_etiquetas() -> None:
    cards = category_cards(NOTES)

    assert [(c.name, c.count, c.percent) for c in cards] == [
        ("Armas y explosivos", 2, 50),
        ("Otros", 1, 25),
        (NO_CATEGORY, 1, 25),
    ]
    assert cards[0].top_state in {"Chihuahua", "Nuevo León"}
    assert cards[0].labels == ("tráfico de armas",)
    assert cards[1].color == OTHER_COLOR


def test_barras_apiladas_por_estado() -> None:
    stacks = state_stacks(NOTES)

    assert [(s.name, s.count) for s in stacks] == [("Chihuahua", 2), ("Nuevo León", 1)]
    assert [(seg.category, seg.count) for seg in stacks[0].segments] == [
        ("Armas y explosivos", 1),
        ("Otros", 1),
    ]
    # El estado con más notas llena la barra completa.
    assert sum(seg.share for seg in stacks[0].segments) == 1


def test_linea_del_tiempo_por_hora_con_picos() -> None:
    line = timeline(NOTES)

    assert line.unit == "hora"
    # 15:00, 16:00, 17:00 … 20:00 de la CDMX.
    assert [b.count for b in line.bars][:3] == [2, 0, 1]
    assert line.bars[0].label == "15 h"
    assert line.peaks[0].when == "25 OCT, 15:00–16:00"
    assert line.peaks[0].count == 2


def test_noticias_por_estado_y_categoria_numeradas_de_corrido() -> None:
    groups = state_groups(NOTES)

    assert [g.name for g in groups] == ["Chihuahua", "Nuevo León", NO_STATE]
    assert [c.name for c in groups[0].categories] == ["Armas y explosivos", "Otros"]
    numbers = [n.number for g in groups for c in g.categories for n in c.notes]
    assert numbers == [1, 2, 3, 4]


def test_insignias_de_confianza() -> None:
    sure = replace(NOTES[0], judgements=(JudgementView(1, "FGR", True, 0.95, "Actúa la FGR."),))
    doubtful = replace(NOTES[1], judgements=(JudgementView(1, "FGR", True, 0.35, None),))

    assert [b.text for b in badges(sure)] == [
        "ARMAS Y EXPLOSIVOS",
        "FGR FEDERAL",
        "CONFIANZA ALTA",
    ]
    assert confidence(doubtful) == "BAJA"
    # Sin saber quién actúa, esa insignia no aparece.
    assert [b.kind for b in badges(doubtful)] == ["category", "confidence"]


def test_la_red_de_la_portada_es_la_misma_para_el_mismo_expediente() -> None:
    assert network_svg("EXP-1") == network_svg("EXP-1")
    assert network_svg("EXP-1") != network_svg("EXP-2")
    assert network_svg("EXP-1").startswith("<svg")


def test_todo_junto() -> None:
    view = build_oraculo(search(), NOTES, datetime(2026, 10, 26, 10, tzinfo=UTC))

    assert view.code == "EXP-20261017-1400"
    assert view.issued == "26 OCT 2026"
    assert (view.states_with_notes, view.top_category, view.automatic) == (
        2,
        "Armas y explosivos",
        False,
    )
