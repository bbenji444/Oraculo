"""Dónde se dibuja cada nodo del muro (Fase 9.6, decisión D3)."""

import math

from app.domain.case_graph import (
    MEXICO_CENTER,
    SPIRAL_STEP_M,
    GeoPoint,
    LayoutItem,
    case_center,
    layout_points,
    node_anchor,
    note_links,
    offset,
    visible_nodes,
)
from app.domain.investigation import EntityType

MIGUEL_HIDALGO = GeoPoint(-99.2, 19.43)
POLANCO = GeoPoint(-99.19, 19.433)


def meters(a: GeoPoint, b: GeoPoint) -> float:
    dy = (b.lat - a.lat) * 111_320
    dx = (b.lon - a.lon) * 111_320 * math.cos(math.radians(a.lat))
    return math.hypot(dx, dy)


def test_un_lugar_ubicado_va_en_su_punto() -> None:
    assert node_anchor(EntityType.PLACE, POLANCO, [MIGUEL_HIDALGO], MIGUEL_HIDALGO) == (
        POLANCO,
        True,
    )


def test_una_persona_va_al_lugar_mas_repetido_de_sus_notas() -> None:
    other = GeoPoint(-103.35, 20.67)
    anchor = node_anchor(EntityType.PERSON, None, [other, MIGUEL_HIDALGO, MIGUEL_HIDALGO], other)

    assert anchor == (MIGUEL_HIDALGO, False)


def test_sin_notas_ubicadas_va_al_centro_del_caso() -> None:
    assert node_anchor(EntityType.ORG, None, [], POLANCO) == (POLANCO, False)
    # Un lugar sin punto del catálogo tampoco se inventa uno.
    assert node_anchor(EntityType.PLACE, None, [], POLANCO) == (POLANCO, False)


def test_el_centro_del_caso_es_el_promedio_o_mexico() -> None:
    assert case_center([GeoPoint(-100, 20), GeoPoint(-98, 18)]) == GeoPoint(-99, 19)
    assert case_center([]) == GeoPoint(*MEXICO_CENTER)


def test_los_que_comparten_ancla_no_se_enciman_y_quedan_cerca() -> None:
    # El caso real: las 8 notas caen en Miguel Hidalgo y todas las personas
    # comparten ancla.
    items = [LayoutItem(n, MIGUEL_HIDALGO, False, 10 - n) for n in range(1, 31)]

    positions = layout_points(items)

    points = list(positions.values())
    closest = min(meters(a, b) for i, a in enumerate(points) for b in points[i + 1 :])
    farthest = max(meters(MIGUEL_HIDALGO, p) for p in points)
    assert len(positions) == 30
    # Espiral de Vogel: separación pareja, sin nodos encimados…
    assert closest > SPIRAL_STEP_M * 0.5
    # …y todos dentro de unos 2 km (la alcaldía en pantalla).
    assert farthest <= SPIRAL_STEP_M * math.sqrt(30) + 1


def test_el_mas_mencionado_queda_mas_cerca_y_siempre_igual() -> None:
    items = [LayoutItem(1, MIGUEL_HIDALGO, False, 1), LayoutItem(2, MIGUEL_HIDALGO, False, 9)]

    first, again = layout_points(items), layout_points(list(reversed(items)))

    assert meters(MIGUEL_HIDALGO, first[2]) < meters(MIGUEL_HIDALGO, first[1])
    assert first == again


def test_un_lugar_fijo_se_queda_en_su_punto_y_los_demas_lo_rodean() -> None:
    items = [LayoutItem(1, POLANCO, True, 3), LayoutItem(2, POLANCO, False, 5)]

    positions = layout_points(items)

    assert positions[1] == POLANCO
    assert meters(POLANCO, positions[2]) > SPIRAL_STEP_M * 0.9


def test_offset_mueve_los_metros_pedidos() -> None:
    moved = offset(MIGUEL_HIDALGO, 300, 400)

    assert abs(meters(MIGUEL_HIDALGO, moved) - 500) < 1


def test_el_tope_deja_los_mas_mencionados() -> None:
    assert visible_nodes({1: 3, 2: 9, 3: 9, 4: 1}, 2) == ([2, 3], 2)
    assert visible_nodes({1: 3}, 150) == ([1], 0)


def test_la_constelacion_une_notas_que_comparten_entidades() -> None:
    links = note_links({10: {1, 2}, 11: {1, 2}, 12: {3}, 13: {2}})

    assert links == {(10, 11): 2, (10, 13): 1, (11, 13): 1}


def test_dos_lugares_en_el_mismo_punto_no_se_enciman() -> None:
    # El caso real: "Polanco" quedó ubicado en su alcaldía, Miguel Hidalgo.
    items = [LayoutItem(3, MIGUEL_HIDALGO, True, 7), LayoutItem(4, MIGUEL_HIDALGO, True, 5)]

    positions = layout_points(items)

    assert positions[3] == MIGUEL_HIDALGO
    assert meters(positions[3], positions[4]) > SPIRAL_STEP_M * 0.9
