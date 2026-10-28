"""Preguntas del analista en el reporte (28/10/2026): sin base, sin IA, sin red."""

from dataclasses import replace
from datetime import timedelta

from app.adapters.reports.oraculo import timeline
from app.adapters.reports.questions import (
    OTHER_ACTION,
    action_of,
    actions,
    build_questions,
    reliability,
    state_cards,
    top_facts,
)
from tests.unit.test_report_oraculo import ARMAS, AT_15, NOTES, OTROS, note


def test_el_tipo_de_hecho_de_la_ia_manda_sobre_el_titulo() -> None:
    # «PAN exige a la FGR investigar…» es una denuncia, no una investigación.
    complaint = replace(
        NOTES[0], title="PAN exige a la FGR investigar a Taddei", event_type="denuncia"
    )
    assert action_of(complaint) == "Denuncias"


def test_sin_tipo_de_hecho_se_lee_el_titulo() -> None:
    assert action_of(replace(NOTES[0], title="FGR detiene a cinco", event_type=None)) == (
        "Detenciones"
    )
    assert action_of(replace(NOTES[0], title="Vinculan a proceso", event_type=None)) == (
        "Procesos judiciales"
    )
    assert action_of(replace(NOTES[0], title="Choque en la autopista", event_type=None)) == (
        OTHER_ACTION
    )


def test_las_actuaciones_van_de_mas_a_menos_y_otros_al_final() -> None:
    notes = (
        replace(NOTES[0], event_type="detención"),
        replace(NOTES[1], event_type="detenciones"),
        replace(NOTES[2], event_type="asalto"),
        replace(NOTES[3], event_type="sentencia"),
    )
    bars = actions(notes)

    assert [(b.name, b.count) for b in bars] == [
        ("Detenciones", 2),
        ("Sentencias", 1),
        (OTHER_ACTION, 1),
    ]
    assert bars[0].share == 1.0


def test_lo_mas_importante_es_lo_que_mas_medios_publicaron() -> None:
    lead = note(30, "08019", ARMAS, AT_15, story_id=30)
    echo = note(31, "08019", ARMAS, AT_15 + timedelta(minutes=5), story_id=30)

    [first, second] = top_facts((*NOTES, lead, echo), limit=2)

    assert (first.rank, first.article.article_id, first.outlets) == (1, 30, 2)
    assert first.state == "Chihuahua"
    assert second.outlets == 1


def test_una_ficha_por_estado_con_su_delito_y_su_hecho() -> None:
    cards = state_cards(NOTES)

    assert [c.name for c in cards] == ["Chihuahua", "Nuevo León"]
    chihuahua = cards[0]
    assert (chihuahua.count, chihuahua.percent) == (2, 50)
    assert sum(s.share for s in chihuahua.segments) == 1.0
    assert chihuahua.main_category in {"Armas y explosivos", "Otros"}


def test_confianza_y_precision_suman_el_total() -> None:
    trust = reliability(NOTES)

    assert [b.name for b in trust.confidence] == ["ALTA", "MEDIA", "BAJA"]
    assert sum(b.count for b in trust.confidence) == len(NOTES)
    assert sum(b.count for b in trust.precision) == len(NOTES)
    # La nota sin lugar cuenta como «Sin ubicación».
    assert trust.precision[-1].count == 1


def test_cada_pregunta_lleva_su_conclusion() -> None:
    view = build_questions(NOTES, timeline(NOTES))

    assert "concentra" in view.lines.crimes
    assert view.lines.places.startswith("Chihuahua encabeza con 2 notas")
    assert "momento con más notas" in view.lines.timing
    assert view.no_state_percent == 25


def test_sin_notas_no_hay_conclusiones() -> None:
    view = build_questions((), timeline(()))

    assert view.lines.crimes == view.lines.places == view.lines.trust == ""
    assert view.top == view.actions == view.states == ()
    assert OTROS.name == "Otros"
