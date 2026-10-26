"""Dónde se dibuja cada cosa del muro de un caso sobre el globo (Fase 9.6, §9.5).

El muro muestra las entidades confirmadas de un caso como nodos sobre el
globo y sus vínculos como arcos. Este módulo decide la posición de cada nodo:

- **Ancla (``node_anchor``):** un lugar va a su punto del catálogo; una
  persona, organización o vehículo va a la ubicación más repetida de sus notas
  (el lugar del hecho); si no hay, al centro del caso.
- **Reparto (``layout_points``):** en un caso real todas las notas suelen caer
  en el mismo municipio, así que muchos nodos comparten ancla. Se acomodan en
  una espiral de Vogel (ángulo áureo) alrededor de ella: quedan separados
  parejo, el más mencionado más cerca, y siempre en el mismo lugar (el
  cálculo es determinista, para que los nodos no "bailen" entre visitas).
- **Tope (``visible_nodes``):** solo los más mencionados, hasta
  ``CASE_MAX_VISIBLE_NODES``.
- **Constelación (``note_links``):** dos notas del caso se unen si comparten
  entidades confirmadas.

La posición de una persona es **visual**: dice "aparece en notas de aquí", no
un domicilio.

Quién lo usa: el caso de uso ``GetCaseGraph``.

No hace: no consulta la base ni dibuja; no decide qué entidades entran (solo
las confirmadas, ADR-0104, lo filtra el caso de uso).
"""

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from app.domain.investigation import EntityType

# Separación base de la espiral, en metros: a zoom 13–14 (una alcaldía en
# pantalla) dos nodos quedan a unos 30–60 px. Decisión de la 9.6.
SPIRAL_STEP_M = 350.0
# Ángulo áureo (π·(3−√5) ≈ 137.5°): reparte puntos parejo en un disco sin que
# se alineen en rayos (espiral de Vogel).
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
# Metros por grado de latitud (esfera de 6,371 km; el globo de MapLibre
# también es esfera, así que la aproximación basta para separar nodos).
METERS_PER_DEGREE = 111_320.0
# Dos anclas a menos de ~1 m son la misma (los puntos vienen del catálogo y se
# repiten exactos; esto solo absorbe el ruido de los flotantes).
ANCHOR_DECIMALS = 5
# Centro aproximado de México, para un caso sin ninguna nota ubicada.
MEXICO_CENTER = (-102.5528, 23.6345)


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """Un punto sobre el globo.

    Attributes:
        lon: Longitud en grados.
        lat: Latitud en grados.
    """

    lon: float
    lat: float

    def key(self) -> tuple[float, float]:
        """El punto redondeado, para saber si dos anclas son la misma."""
        return round(self.lon, ANCHOR_DECIMALS), round(self.lat, ANCHOR_DECIMALS)


@dataclass(frozen=True, slots=True)
class LayoutItem:
    """Algo que se acomoda alrededor de un ancla.

    Attributes:
        item_id: Identificador (entidad o nota).
        anchor: Punto alrededor del cual se acomoda.
        pinned: Si va exactamente en el ancla (un lugar es su propio punto).
        weight: Cuánto pesa (menciones o entidades): el más pesado, más cerca.
    """

    item_id: int
    anchor: GeoPoint
    pinned: bool
    weight: int


def case_center(points: Iterable[GeoPoint]) -> GeoPoint:
    """El centro del caso: el promedio de las ubicaciones de sus notas.

    Args:
        points: Ubicación principal de cada nota del caso.

    Returns:
        El promedio, o el centro de México si ninguna nota está ubicada.
    """
    found = list(points)
    if not found:
        return GeoPoint(*MEXICO_CENTER)
    return GeoPoint(sum(p.lon for p in found) / len(found), sum(p.lat for p in found) / len(found))


def node_anchor(
    kind: EntityType,
    own_point: GeoPoint | None,
    article_points: Sequence[GeoPoint],
    center: GeoPoint,
) -> tuple[GeoPoint, bool]:
    """Dónde se ancla un nodo del muro (decisión D3).

    Args:
        kind: Tipo de entidad.
        own_point: Punto del catálogo de la entidad (solo lugares ya ubicados).
        article_points: Ubicación principal de cada nota donde aparece.
        center: Centro del caso.

    Returns:
        El ancla y si el nodo va exactamente en ella (``pinned``).

    Example:
        >>> node_anchor(EntityType.PLACE, GeoPoint(-99.19, 19.43), [], GeoPoint(0, 0))
        (GeoPoint(lon=-99.19, lat=19.43), True)
    """
    if kind is EntityType.PLACE and own_point is not None:
        return own_point, True
    if article_points:
        # La más repetida; si empatan, la de la nota que llegó primero a la lista.
        counts = Counter(p.key() for p in article_points)
        best = max(counts.values())
        return next(p for p in article_points if counts[p.key()] == best), False
    return center, False


def offset(point: GeoPoint, east_m: float, north_m: float) -> GeoPoint:
    """El punto movido unos metros al este y al norte.

    Args:
        point: Punto de partida.
        east_m: Metros hacia el este (negativo: oeste).
        north_m: Metros hacia el norte (negativo: sur).

    Returns:
        El punto nuevo.
    """
    cos_lat = max(math.cos(math.radians(point.lat)), 1e-6)
    return GeoPoint(
        point.lon + east_m / (METERS_PER_DEGREE * cos_lat),
        point.lat + north_m / METERS_PER_DEGREE,
    )


def layout_points(items: Sequence[LayoutItem]) -> dict[int, GeoPoint]:
    """Posición final de cada elemento: su ancla o su lugar en la espiral (D3).

    Los que van fijos se quedan en su ancla. Los demás se acomodan alrededor
    de la suya en una espiral de Vogel: el k-ésimo a ``SPIRAL_STEP_M·√k``
    metros y ``k·GOLDEN_ANGLE`` de giro, ordenados del más pesado al más
    ligero (y por id, para que siempre salga igual). Si en el ancla hay un
    fijo, la espiral empieza en el anillo 1 para no taparlo.

    Args:
        items: Lo que se acomoda.

    Returns:
        Posición de cada ``item_id``.
    """
    groups: dict[tuple[float, float], list[LayoutItem]] = {}
    for item in items:
        groups.setdefault(item.anchor.key(), []).append(item)
    positions: dict[int, GeoPoint] = {}
    for group in groups.values():
        by_weight = sorted(group, key=lambda i: (not i.pinned, -i.weight, i.item_id))
        # Solo un fijo se queda en el ancla: si el catálogo ubicó dos lugares en el
        # mismo punto ("Polanco" quedó en su alcaldía), el otro se acomoda alrededor.
        loose = by_weight
        if by_weight[0].pinned:
            positions[by_weight[0].item_id] = by_weight[0].anchor
            loose = by_weight[1:]
        # Sin nada fijo, el primero también se separa un poco del ancla: el
        # punto del municipio suele ser el de la nota y conviene ver ambos.
        for index, item in enumerate(loose, start=1):
            radius = SPIRAL_STEP_M * math.sqrt(index)
            angle = index * GOLDEN_ANGLE
            positions[item.item_id] = offset(
                item.anchor, radius * math.cos(angle), radius * math.sin(angle)
            )
    return positions


def visible_nodes(weights: Mapping[int, int], limit: int) -> tuple[list[int], int]:
    """Qué nodos se dibujan cuando hay más que el tope (D8).

    Args:
        weights: Menciones de cada entidad.
        limit: Cuántos como máximo (``CASE_MAX_VISIBLE_NODES``).

    Returns:
        Los ids que se dibujan (los más mencionados; si empatan, el de id
        menor) y cuántos quedaron fuera.
    """
    ordered = sorted(weights, key=lambda entity: (-weights[entity], entity))
    return ordered[:limit], max(len(ordered) - limit, 0)


def note_links(entities_by_note: Mapping[int, set[int]]) -> dict[tuple[int, int], int]:
    """Pares de notas que comparten entidades confirmadas (constelación, D7).

    Args:
        entities_by_note: Entidades confirmadas visibles de cada nota.

    Returns:
        Cada par de notas (id menor primero) con cuántas entidades comparten.
    """
    notes_by_entity: dict[int, list[int]] = {}
    for note, entities in entities_by_note.items():
        for entity in entities:
            notes_by_entity.setdefault(entity, []).append(note)
    links: Counter[tuple[int, int]] = Counter()
    for notes in notes_by_entity.values():
        for first, second in combinations(sorted(set(notes)), 2):
            links[(first, second)] += 1
    return dict(links)
