"""Reporte menos saturado (28/10/2026): dona, barras por categoría, destacados e índice con tope.

Benji: «no quiero saturarlo de noticias… prefiero resúmenes, gráficas, datos
importantes». Sin base, sin IA, sin red.
"""

from datetime import timedelta

from app.adapters.reports.oraculo import (
    category_cards,
    donut,
    highlights,
    limit_groups,
    state_groups,
    timeline,
)
from tests.unit.test_report_oraculo import ARMAS, AT_15, NOTES, OTROS, note


def test_la_dona_reparte_la_vuelta_entre_las_categorias() -> None:
    slices = donut(category_cards(NOTES))

    assert [s.name for s in slices] == ["Armas y explosivos", "Otros", "Sin clasificar"]
    assert [s.count for s in slices] == [2, 1, 1]
    # Cada tramo es un trazo cerrado hecho solo de números.
    assert all(s.path.startswith("M") and s.path.endswith("Z") for s in slices)
    assert all("<" not in s.path for s in slices)


def test_una_sola_categoria_llena_la_dona_sin_desaparecer() -> None:
    [whole] = donut(category_cards(NOTES[:1]))

    # El arco SVG de 360° no se dibuja: se deja casi la vuelta completa.
    assert " 0 1 1 " in whole.path


def test_cada_barra_de_la_linea_del_tiempo_va_por_categoria() -> None:
    first = timeline(NOTES).bars[0]

    # A las 15:00 hubo una de armas y una de «Otros».
    assert [(s.category, s.count) for s in first.segments] == [
        ("Armas y explosivos", 1),
        ("Otros", 1),
    ]
    assert sum(s.share for s in first.segments) == first.share


def test_con_pocas_horas_se_rotulan_todas() -> None:
    # Una corrida cubre 8 horas: antes solo se leían «23 h» y «05 h».
    assert all(bar.label for bar in timeline(NOTES).bars)


def test_destacan_los_hechos_que_mas_medios_publicaron_en_orden_de_hora() -> None:
    lead = note(20, "08019", ARMAS, AT_15, story_id=20, source_name="Uno")
    echo = note(21, "08019", ARMAS, AT_15 + timedelta(minutes=30), story_id=20)
    alone = note(22, "19039", OTROS, AT_15 - timedelta(hours=1))
    later = note(23, "19039", OTROS, AT_15 + timedelta(hours=2))

    chosen = highlights((later, echo, lead, alone), limit=2)

    # El de dos medios entra; del resto, el más reciente. Se muestran por hora.
    assert [h.article.article_id for h in chosen] == [20, 23]
    assert chosen[0].outlets == 2
    assert chosen[0].also == (echo,)
    assert chosen[0].state == "Chihuahua"


def test_el_indice_tiene_tope_y_conserva_la_numeracion() -> None:
    many = tuple(note(100 + i, "08019", OTROS, AT_15 + timedelta(minutes=i)) for i in range(7))

    groups, omitted = limit_groups(state_groups(many), max_facts=5)

    listed = [n.number for g in groups for c in g.categories for n in c.notes]
    assert listed == [1, 2, 3, 4, 5]
    assert omitted == 2


def test_sin_tope_alcanzado_no_se_omite_nada() -> None:
    groups, omitted = limit_groups(state_groups(NOTES))

    assert omitted == 0
    assert sum(len(c.notes) for g in groups for c in g.categories) == len(NOTES)
