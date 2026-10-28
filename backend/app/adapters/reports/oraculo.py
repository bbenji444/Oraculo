"""Secciones del reporte con el lenguaje visual de Oráculo (F12.10, ADR-0033).

Benji pidió un reporte «mucho más dinámico, muy visual, muy formal», con lo
que les gustó a sus jefes (el mapa de México con porcentajes) y «más cosas
así»: categorías, línea del tiempo y las noticias divididas por estado con
despliegue tipo chevron. El lenguaje visual se homologa con los expedientes
de Oráculo 2.0: número de expediente, banda de confidencialidad e insignias
de confianza.

Aquí se calcula todo eso a partir de las notas relevantes, sin IA:

- ``expediente``: el número del reporte (``EXP-FGR-20261025-2300``).
- ``category_cards``: una tarjeta por categoría, con su estado principal y las
  etiquetas libres más repetidas.
- ``state_stacks``: barras apiladas por categoría en cada estado.
- ``timeline``: notas por hora o por día (fecha de publicación, hora de la
  CDMX, ADR-0032) con los 3 picos y la nota principal de cada uno.
- ``donut``: la dona de las notas por categoría.
- ``highlights``: los hechos más importantes, en orden de hora, para la
  cronología del reporte (los que más medios publicaron).
- ``state_groups`` y ``limit_groups``: Estado ▸ Categoría ▸ Noticias,
  numeradas para citarlas, con un tope para no saturar el PDF.
- ``badges``: las insignias de cada nota (categoría, quién actúa, confianza).
- ``network_svg``: la red de nodos de la portada.
- ``clean``: quita emojis y símbolos que la fuente del PDF no tiene.

No hace: no dibuja la plantilla ni decide qué notas entran (eso es
``BuildReport``). Los colores de las categorías son provisionales: los
definitivos se deciden con datos (ADR-0029).
"""

import math
import random
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.clock import MEXICO_CITY
from app.application.ports.search_reads import ArticleItem, PreviousRun, SearchDetail
from app.domain.authority import AUTHORITY_LABEL, Authority

PERCENT = 100
# Colores provisionales por categoría (orden del catálogo), legibles impresos
# y en pantalla junto al cian de Oráculo. «Otros» va en gris.
CATEGORY_PALETTE = (
    "#0090b8",
    "#d6455d",
    "#e0a100",
    "#1aa37a",
    "#7c5cd6",
    "#d0569e",
    "#3b82c4",
    "#c2410c",
    "#0f766e",
    "#a16207",
    "#4f46e5",
    "#be185d",
    "#15803d",
)
OTHER_COLOR = "#8a9aa3"
NO_CATEGORY = "Sin clasificar"
NO_STATE = "Sin estado identificado"
# Estados en las barras apiladas: los demás se suman en «Otros estados».
MAX_STACK_STATES = 12
# Etiquetas libres de la IA por tarjeta de categoría.
MAX_CARD_LABELS = 3
# Hasta 3 días se cuenta por hora; con más, por día (igual que el monitor, ADR-0032).
HOURLY_UP_TO = timedelta(days=3)
PEAKS = 3
# Benji, 28/10/2026: «no quiero saturarlo de noticias… prefiero resúmenes,
# gráficas, datos importantes». La cronología lleva los hechos más importantes
# con su resumen, y el índice lista los demás en un renglón cada uno, hasta un
# tope; el resto se consulta en el sistema o en el CSV.
MAX_HIGHLIGHTS = 8
MAX_LISTED_FACTS = 40
# Dona de categorías: radios externo e interno en el lienzo de 120 × 120.
DONUT_OUTER = 56.0
DONUT_INNER = 34.0
DONUT_CENTER = 60.0
# Una sola categoría ocupa la vuelta entera; el arco SVG no dibuja 360°.
FULL_TURN = 0.9999
# Pasando media vuelta el arco SVG toma el camino largo (bandera large-arc).
HALF_TURN = 0.5
# Umbrales de la insignia de confianza (puntaje de relevancia de la IA, 0 a 1).
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.6
# Red de la portada: nodos y distancia máxima para unirlos (en unidades del lienzo).
NETWORK_NODES = 46
NETWORK_LINK_DISTANCE = 150
NETWORK_WIDTH = 800
NETWORK_HEIGHT = 520

STATE_NAMES: dict[str, str] = {
    "01": "Aguascalientes",
    "02": "Baja California",
    "03": "Baja California Sur",
    "04": "Campeche",
    "05": "Coahuila",
    "06": "Colima",
    "07": "Chiapas",
    "08": "Chihuahua",
    "09": "Ciudad de México",
    "10": "Durango",
    "11": "Guanajuato",
    "12": "Guerrero",
    "13": "Hidalgo",
    "14": "Jalisco",
    "15": "Estado de México",
    "16": "Michoacán",
    "17": "Morelos",
    "18": "Nayarit",
    "19": "Nuevo León",
    "20": "Oaxaca",
    "21": "Puebla",
    "22": "Querétaro",
    "23": "Quintana Roo",
    "24": "San Luis Potosí",
    "25": "Sinaloa",
    "26": "Sonora",
    "27": "Tabasco",
    "28": "Tamaulipas",
    "29": "Tlaxcala",
    "30": "Veracruz",
    "31": "Yucatán",
    "32": "Zacatecas",
}
STATE_CODE_DIGITS = 2
MONTHS = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")


def clean(text: str | None) -> str:
    """Quita emojis y símbolos gráficos que la fuente del PDF no puede dibujar.

    Los títulos de algunos medios traen «👉» o «🎦»; en el PDF salían como un
    cuadro vacío. Se conservan letras, números, puntuación y comillas.

    Args:
        text: Texto de la nota.

    Returns:
        El texto sin esos símbolos y sin espacios dobles.
    """
    if not text:
        return ""
    kept = (
        ch
        for ch in text
        if unicodedata.category(ch) not in {"So", "Cs", "Co"} and ch not in {"‍", "️", "︎"}
    )
    return " ".join("".join(kept).split())


def state_code(article: ArticleItem) -> str | None:
    """Clave INEGI del estado de la ubicación principal (``08`` de ``08019``)."""
    code = article.primary.region_code if article.primary else None
    # Las claves INEGI empiezan con los 2 dígitos del estado; las de país son letras.
    state = (code or "")[:STATE_CODE_DIGITS]
    return state if state in STATE_NAMES else None


def state_name(article: ArticleItem) -> str:
    """Nombre del estado de la nota, o «Sin estado identificado»."""
    code = state_code(article)
    return STATE_NAMES[code] if code else NO_STATE


def category_name(article: ArticleItem) -> str:
    """Nombre de la categoría de la nota, o «Sin clasificar»."""
    return article.category.name if article.category else NO_CATEGORY


def category_color(article: ArticleItem) -> str:
    """Color provisional de la categoría de la nota."""
    category = article.category
    if category is None or category.name == "Otros":
        return OTHER_COLOR
    if category.color:
        return category.color
    return CATEGORY_PALETTE[(category.category_id - 1) % len(CATEGORY_PALETTE)]


def _percent(count: int, total: int) -> int:
    return round(PERCENT * count / total) if total else 0


def expediente(search: SearchDetail) -> str:
    """Número del reporte, como los expedientes de Oráculo 2.0.

    Args:
        search: La búsqueda.

    Returns:
        ``EXP-FGR-20261025-2300`` para una corrida automática (su hora
        programada en la CDMX) o ``EXP-20261024-1236`` para una manual.
    """
    moment = (search.scheduled_for or search.created_at).astimezone(MEXICO_CITY)
    kind = "FGR-" if search.scheduled_for else ""
    return f"EXP-{kind}{moment:%Y%m%d-%H%M}"


def date_caps(moment: datetime) -> str:
    """Fecha como en los expedientes de Oráculo: ``25 OCT 2026``."""
    local = moment.astimezone(MEXICO_CITY)
    return f"{local.day:02d} {MONTHS[local.month - 1]} {local.year}"


@dataclass(frozen=True, slots=True)
class CategoryCard:
    """Una tarjeta de categoría.

    Attributes:
        name: Categoría.
        color: Su color provisional.
        count: Notas.
        percent: Porcentaje de las notas relevantes.
        top_state: Estado con más notas de esta categoría, o vacío.
        labels: Etiquetas libres de la IA más repetidas («robo de combustible»).
    """

    name: str
    color: str
    count: int
    percent: int
    top_state: str
    labels: tuple[str, ...]


def category_cards(articles: Sequence[ArticleItem]) -> tuple[CategoryCard, ...]:
    """Una tarjeta por categoría, de la que tiene más notas a la que menos.

    Args:
        articles: Notas relevantes.

    Returns:
        Las tarjetas («Otros» y «Sin clasificar» al final).
    """
    by_name: dict[str, list[ArticleItem]] = defaultdict(list)
    for article in articles:
        by_name[category_name(article)].append(article)
    cards = []
    for name, members in by_name.items():
        states = Counter(state_name(a) for a in members if state_code(a))
        labels = Counter(
            clean(a.category_raw).lower()
            for a in members
            if a.category_raw and clean(a.category_raw)
        )
        cards.append(
            CategoryCard(
                name=name,
                color=category_color(members[0]),
                count=len(members),
                percent=_percent(len(members), len(articles)),
                top_state=states.most_common(1)[0][0] if states else "",
                labels=tuple(label for label, _ in labels.most_common(MAX_CARD_LABELS)),
            )
        )
    last = {"Otros": 1, NO_CATEGORY: 2}
    return tuple(sorted(cards, key=lambda c: (last.get(c.name, 0), -c.count, c.name)))


@dataclass(frozen=True, slots=True)
class Segment:
    """Un tramo de una barra apilada.

    Attributes:
        category: Categoría.
        color: Su color.
        count: Notas.
        share: Ancho del tramo respecto al estado con más notas (0 a 1).
    """

    category: str
    color: str
    count: int
    share: float


@dataclass(frozen=True, slots=True)
class StateStack:
    """Un estado con sus notas repartidas por categoría.

    Attributes:
        name: Estado.
        count: Notas.
        percent: Porcentaje de las notas relevantes.
        segments: Tramos por categoría, de mayor a menor.
    """

    name: str
    count: int
    percent: int
    segments: tuple[Segment, ...]


def state_stacks(articles: Sequence[ArticleItem]) -> tuple[StateStack, ...]:
    """Barras apiladas por categoría de los estados con más notas.

    Args:
        articles: Notas relevantes.

    Returns:
        Hasta ``MAX_STACK_STATES`` estados, de más a menos notas. Las notas sin
        estado no entran (ya se cuentan en el mapa como «sin ubicación»).
    """
    by_state: dict[str, list[ArticleItem]] = defaultdict(list)
    for article in articles:
        if state_code(article):
            by_state[state_name(article)].append(article)
    ranked = sorted(by_state.items(), key=lambda item: (-len(item[1]), item[0]))
    top = len(ranked[0][1]) if ranked else 0
    stacks = []
    for name, members in ranked[:MAX_STACK_STATES]:
        colors = {category_name(a): category_color(a) for a in members}
        counts = Counter(category_name(a) for a in members)
        segments = tuple(
            Segment(category, colors[category], count, count / top)
            for category, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        )
        stacks.append(
            StateStack(name, len(members), _percent(len(members), len(articles)), segments)
        )
    return tuple(stacks)


@dataclass(frozen=True, slots=True)
class TimeBar:
    """Una barra de la línea del tiempo.

    Attributes:
        start: Inicio del tramo (hora de la CDMX).
        label: Rótulo del eje («15 h», «25 OCT»), o vacío si no se rotula.
        count: Notas publicadas en el tramo.
        share: Alto respecto al tramo más alto (0 a 1).
        peak: Si es uno de los picos.
        segments: La barra partida por categoría, del color de cada una (como
            los puntos del globo); ``share`` de cada tramo respecto al tramo
            más alto.
    """

    start: datetime
    label: str
    count: int
    share: float
    peak: bool
    segments: tuple[Segment, ...] = ()


@dataclass(frozen=True, slots=True)
class Peak:
    """Un pico de la línea del tiempo, con la nota que lo explica.

    Attributes:
        when: Cuándo («25 OCT, 15:00–16:00»).
        count: Notas.
        lead: Título de la nota más reciente del pico.
    """

    when: str
    count: int
    lead: str


@dataclass(frozen=True, slots=True)
class Timeline:
    """Notas por hora o por día y sus picos.

    Attributes:
        unit: ``hora`` o ``día``.
        bars: Tramos, con los vacíos entre la primera y la última nota.
        peaks: Los picos, del más alto al más bajo.
    """

    unit: str
    bars: tuple[TimeBar, ...]
    peaks: tuple[Peak, ...]


# Cada cuántas barras se rotula el eje para que los rótulos no se encimen.
_LABEL_EVERY = {"hora": 6, "día": 2}
# Con pocas barras (una corrida cubre 8 horas) se rotulan todas: con una cada
# 6 horas solo se leían «23 h» y «05 h» (PDF del 28/10/2026).
LABEL_ALL_UP_TO = 12


def timeline(articles: Sequence[ArticleItem]) -> Timeline:
    """La línea del tiempo por fecha de publicación (hora de la CDMX, ADR-0032).

    Args:
        articles: Notas relevantes.

    Returns:
        Por hora si caben en 3 días; si no, por día. Vacía sin notas con fecha.
    """
    dated = sorted(
        ((a.published_at.astimezone(MEXICO_CITY), a) for a in articles if a.published_at),
        key=lambda item: (item[0], item[1].article_id),
    )
    if not dated:
        return Timeline("hora", (), ())
    first, last = dated[0][0], dated[-1][0]
    hourly = last - first <= HOURLY_UP_TO
    unit = "hora" if hourly else "día"
    step = timedelta(hours=1) if hourly else timedelta(days=1)

    def floor(moment: datetime) -> datetime:
        start = moment.replace(minute=0, second=0, microsecond=0)
        return start if hourly else start.replace(hour=0)

    buckets: dict[datetime, list[ArticleItem]] = defaultdict(list)
    for moment, article in dated:
        buckets[floor(moment)].append(article)
    starts = []
    cursor = floor(first)
    while cursor <= last:
        starts.append(cursor)
        cursor += step
    top = max(len(v) for v in buckets.values())
    peak_starts = sorted(
        (s for s in starts if buckets.get(s)), key=lambda s: (-len(buckets[s]), s)
    )[:PEAKS]
    every = 1 if len(starts) <= LABEL_ALL_UP_TO else _LABEL_EVERY[unit]
    bars = tuple(
        TimeBar(
            start=start,
            label=_axis_label(start, hourly) if index % every == 0 else "",
            count=len(buckets.get(start, [])),
            share=len(buckets.get(start, [])) / top,
            peak=start in peak_starts,
            segments=_segments(buckets.get(start, []), top),
        )
        for index, start in enumerate(starts)
    )
    peaks = tuple(
        Peak(
            when=_peak_label(start, hourly),
            count=len(buckets[start]),
            lead=clean(buckets[start][-1].title),
        )
        for start in peak_starts
    )
    return Timeline(unit, bars, peaks)


def _segments(members: Sequence[ArticleItem], top: int) -> tuple[Segment, ...]:
    """Una barra partida por categoría, de la que tiene más notas a la que menos."""
    colors = {category_name(a): category_color(a) for a in members}
    counts = Counter(category_name(a) for a in members)
    return tuple(
        Segment(category, colors[category], count, count / top)
        for category, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def _axis_label(start: datetime, hourly: bool) -> str:
    if not hourly or start.hour == 0:
        return f"{start.day:02d} {MONTHS[start.month - 1]}"
    return f"{start.hour:02d} h"


def _peak_label(start: datetime, hourly: bool) -> str:
    day = f"{start.day:02d} {MONTHS[start.month - 1]}"
    if not hourly:
        return day
    end = start + timedelta(hours=1)
    return f"{day}, {start:%H:%M}–{end:%H:%M}"


@dataclass(frozen=True, slots=True)
class Badge:
    """Una insignia de una nota (estilo de los expedientes de Oráculo 2.0).

    Attributes:
        text: Texto («FGR FEDERAL», «CONFIANZA ALTA»).
        kind: Estilo: ``category``, ``authority``, ``confidence`` o ``ai``.
        color: Color de fondo, si lo lleva (las categorías).
    """

    text: str
    kind: str
    color: str = ""


def confidence(article: ArticleItem) -> str:
    """Confianza de la IA en que la nota es relevante: ALTA, MEDIA o BAJA."""
    scores = [j.relevance_score for j in article.judgements if j.is_relevant]
    best = max(scores, default=0.0)
    if best >= HIGH_CONFIDENCE:
        return "ALTA"
    if best >= MEDIUM_CONFIDENCE:
        return "MEDIA"
    return "BAJA"


def badges(article: ArticleItem) -> tuple[Badge, ...]:
    """Las insignias de una nota: categoría, quién actúa y confianza.

    Args:
        article: La nota.

    Returns:
        Las insignias, en ese orden. Quién actúa solo si se sabe.
    """
    items = [Badge(category_name(article).upper(), "category", category_color(article))]
    if article.authority and article.authority is not Authority.UNKNOWN:
        items.append(Badge(AUTHORITY_LABEL[article.authority].upper(), "authority"))
    items.append(Badge(f"CONFIANZA {confidence(article)}", "confidence"))
    return tuple(items)


@dataclass(frozen=True, slots=True)
class NumberedNote:
    """Una nota con su número de cita y sus insignias.

    Attributes:
        number: Número corrido en todo el reporte.
        article: La nota (la primera que se publicó de su historia).
        badges: Sus insignias.
        also: Las demás notas del mismo hecho en otros medios (ADR-0026), de
            la primera a la última. Se citan con su medio y link, sin repetir
            el resumen.
    """

    number: int
    article: ArticleItem
    badges: tuple[Badge, ...]
    also: tuple[ArticleItem, ...] = ()


@dataclass(frozen=True, slots=True)
class CategoryGroup:
    """Las notas de una categoría dentro de un estado.

    Attributes:
        name: Categoría.
        color: Su color.
        notes: Sus notas numeradas, de la más reciente a la más vieja.
    """

    name: str
    color: str
    notes: tuple[NumberedNote, ...]


@dataclass(frozen=True, slots=True)
class StateGroup:
    """Las notas de un estado, divididas por categoría.

    Attributes:
        name: Estado.
        count: Notas (contando todos los medios, como el mapa).
        percent: Porcentaje de las notas relevantes.
        categories: Sus categorías, de la que tiene más notas a la que menos.
        facts: Hechos distintos (las notas del mismo hecho cuentan una vez).
    """

    name: str
    count: int
    percent: int
    categories: tuple[CategoryGroup, ...]
    facts: int = 0


def _stories(articles: Sequence[ArticleItem]) -> list[tuple[ArticleItem, tuple[ArticleItem, ...]]]:
    """Junta las notas del mismo hecho: la primera publicada y las demás.

    Conserva el orden de ``articles`` (el de la nota más reciente de cada
    historia). Una nota sin historia es un hecho de una sola nota.
    """

    def published(article: ArticleItem) -> tuple[datetime, int]:
        return (article.published_at or datetime.max.replace(tzinfo=UTC), article.article_id)

    by_story: dict[int, list[ArticleItem]] = {}
    for article in articles:
        key = article.story_id if article.story_id is not None else -article.article_id
        by_story.setdefault(key, []).append(article)
    stories = []
    for members in by_story.values():
        ordered = sorted(members, key=published)
        stories.append((ordered[0], tuple(ordered[1:])))
    return stories


Story = tuple[ArticleItem, tuple[ArticleItem, ...]]


def _members(story: Story) -> tuple[ArticleItem, ...]:
    lead, also = story
    return (lead, *also)


def _is_known(story: Story, known: frozenset[int]) -> bool:
    """Si alguna nota del hecho ya venía en la corrida anterior."""
    return any(a.article_id in known for a in _members(story))


def new_facts_only(articles: Sequence[ArticleItem], known: frozenset[int]) -> list[ArticleItem]:
    """Las notas de los hechos que no traía la corrida anterior.

    Benji, 27/10/2026: «solo hechos nuevos cada corrida, para no saturarnos de
    información repetitiva». Un hecho ya reportado se queda fuera completo,
    aunque hoy lo publique un medio más: no es un hecho nuevo.

    Args:
        articles: Notas relevantes de la corrida.
        known: Notas de la corrida anterior.

    Returns:
        Las notas de los hechos nuevos, en el orden de ``articles``.
    """
    fresh = {
        a.article_id
        for story in _stories(articles)
        if not _is_known(story, known)
        for a in _members(story)
    }
    return [a for a in articles if a.article_id in fresh]


def state_groups(articles: Sequence[ArticleItem]) -> tuple[StateGroup, ...]:
    """Estado ▸ Categoría ▸ Hechos, numerados de corrido para citarlos.

    El mismo hecho publicado por varios medios es una sola ficha, con la nota
    que se publicó primero y «También lo publicaron» (ADR-0026). En la corrida
    FGR del 26/10/2026 el reporte traía 113 fichas con resúmenes casi iguales
    («Estoy bien y muy fuerte» en varios medios). El estado y la categoría son
    los de esa primera nota.

    Args:
        articles: Notas relevantes, de la más reciente a la más vieja.

    Returns:
        Los estados de más a menos notas; las notas sin estado al final.
    """
    by_state: dict[str, list[tuple[ArticleItem, tuple[ArticleItem, ...]]]] = defaultdict(list)
    for lead, also in _stories(articles):
        by_state[state_name(lead)].append((lead, also))

    def size(stories: list[tuple[ArticleItem, tuple[ArticleItem, ...]]]) -> int:
        return sum(1 + len(also) for _, also in stories)

    ranked = sorted(
        by_state.items(), key=lambda item: (item[0] == NO_STATE, -size(item[1]), item[0])
    )
    number = 0
    groups = []
    for name, stories in ranked:
        by_category: dict[str, list[tuple[ArticleItem, tuple[ArticleItem, ...]]]] = defaultdict(
            list
        )
        for lead, also in stories:
            by_category[category_name(lead)].append((lead, also))
        categories = []
        for category, members in sorted(
            by_category.items(), key=lambda item: (-size(item[1]), item[0])
        ):
            numbered = []
            for lead, also in members:
                number += 1
                numbered.append(NumberedNote(number, lead, badges(lead), also))
            categories.append(
                CategoryGroup(category, category_color(members[0][0]), tuple(numbered))
            )
        count = size(stories)
        groups.append(
            StateGroup(name, count, _percent(count, len(articles)), tuple(categories), len(stories))
        )
    return tuple(groups)


@dataclass(frozen=True, slots=True)
class DonutSlice:
    """Un tramo de la dona de categorías.

    Attributes:
        name: Categoría.
        color: Su color.
        count: Notas.
        percent: Porcentaje de las notas relevantes.
        path: Trazo SVG del tramo (``d`` de un ``<path>``), solo números.
    """

    name: str
    color: str
    count: int
    percent: int
    path: str


def _arc_point(radius: float, turn: float) -> tuple[float, float]:
    angle = 2 * math.pi * turn - math.pi / 2
    return DONUT_CENTER + radius * math.cos(angle), DONUT_CENTER + radius * math.sin(angle)


def donut(cards: Sequence[CategoryCard]) -> tuple[DonutSlice, ...]:
    """La dona de las notas por categoría, en el orden de las tarjetas.

    Args:
        cards: Las tarjetas por categoría (``category_cards``).

    Returns:
        Un tramo por categoría, empezando arriba y en el sentido del reloj.
    """
    total = sum(card.count for card in cards)
    slices = []
    start = 0.0
    for card in cards:
        share = min(card.count / total, FULL_TURN) if total else 0.0
        end = start + share
        x1, y1 = _arc_point(DONUT_OUTER, start)
        x2, y2 = _arc_point(DONUT_OUTER, end)
        x3, y3 = _arc_point(DONUT_INNER, end)
        x4, y4 = _arc_point(DONUT_INNER, start)
        large = 1 if share > HALF_TURN else 0
        path = (
            f"M{x1:.2f} {y1:.2f} A{DONUT_OUTER} {DONUT_OUTER} 0 {large} 1 {x2:.2f} {y2:.2f} "
            f"L{x3:.2f} {y3:.2f} A{DONUT_INNER} {DONUT_INNER} 0 {large} 0 {x4:.2f} {y4:.2f} Z"
        )
        slices.append(DonutSlice(card.name, card.color, card.count, card.percent, path))
        start = end
    return tuple(slices)


@dataclass(frozen=True, slots=True)
class Highlight:
    """Un hecho destacado de la cronología del reporte.

    Attributes:
        article: La primera nota que se publicó del hecho.
        outlets: Cuántos medios lo publicaron (la nota y las demás del hecho).
        state: Estado del hecho.
        color: Color de su categoría.
        badges: Sus insignias.
        also: Las demás notas del mismo hecho.
    """

    article: ArticleItem
    outlets: int
    state: str
    color: str
    badges: tuple[Badge, ...]
    also: tuple[ArticleItem, ...] = ()


def _best_score(article: ArticleItem) -> float:
    return max((j.relevance_score for j in article.judgements if j.is_relevant), default=0.0)


def highlights(
    articles: Sequence[ArticleItem], limit: int = MAX_HIGHLIGHTS
) -> tuple[Highlight, ...]:
    """Los hechos más importantes, para la cronología del reporte.

    Importa más el hecho que publicaron más medios; entre iguales, el que la
    IA juzgó más relevante y luego el más reciente. Se muestran en orden de
    hora, como la cronología del monitor.

    Args:
        articles: Notas relevantes.
        limit: Cuántos hechos.

    Returns:
        Hasta ``limit`` hechos, del primero al último que se publicó.
    """

    def importance(story: Story) -> tuple[int, float, float]:
        lead, also = story
        moment = lead.published_at.timestamp() if lead.published_at else 0.0
        return (-(1 + len(also)), -_best_score(lead), -moment)

    chosen = sorted(_stories(articles), key=importance)[:limit]

    def when(story: Story) -> tuple[datetime, int]:
        lead = story[0]
        return (lead.published_at or datetime.max.replace(tzinfo=UTC), lead.article_id)

    return tuple(
        Highlight(lead, 1 + len(also), state_name(lead), category_color(lead), badges(lead), also)
        for lead, also in sorted(chosen, key=when)
    )


def limit_groups(
    groups: Sequence[StateGroup], max_facts: int = MAX_LISTED_FACTS
) -> tuple[tuple[StateGroup, ...], int]:
    """Recorta el índice de noticias a ``max_facts`` hechos.

    Se conservan los estados con más notas primero (el orden de
    ``state_groups``) y la numeración original, para que las citas no cambien.

    Args:
        groups: Estado ▸ Categoría ▸ Noticias.
        max_facts: Cuántos hechos caben en el índice.

    Returns:
        Los grupos recortados y cuántos hechos quedaron fuera.
    """
    kept: list[StateGroup] = []
    room = max_facts
    omitted = 0
    for group in groups:
        categories = []
        for category in group.categories:
            notes = category.notes[: max(room, 0)]
            omitted += len(category.notes) - len(notes)
            room -= len(notes)
            if notes:
                categories.append(CategoryGroup(category.name, category.color, notes))
        if categories:
            kept.append(
                StateGroup(group.name, group.count, group.percent, tuple(categories), group.facts)
            )
    return tuple(kept), omitted


def network_svg(seed: str) -> str:
    """La red de nodos de la portada (como las portadas de Oráculo 2.0).

    Se genera con una semilla fija por reporte: el mismo reporte siempre
    dibuja la misma red, y no hace falta ninguna imagen externa.

    Args:
        seed: Semilla (el número de expediente).

    Returns:
        Un ``<svg>`` con nodos y conexiones en cian sobre transparente.
    """
    rng = random.Random(seed)  # noqa: S311 — dibujo decorativo, no criptografía
    nodes = [
        (rng.uniform(0, NETWORK_WIDTH), rng.uniform(0, NETWORK_HEIGHT), rng.uniform(1.2, 3.6))
        for _ in range(NETWORK_NODES)
    ]
    lines = []
    for i, (x1, y1, _) in enumerate(nodes):
        for x2, y2, _ in nodes[i + 1 :]:
            distance = math.hypot(x2 - x1, y2 - y1)
            if distance < NETWORK_LINK_DISTANCE:
                opacity = 0.55 * (1 - distance / NETWORK_LINK_DISTANCE)
                lines.append(
                    f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                    f'stroke="#00d2ff" stroke-opacity="{opacity:.2f}" stroke-width="0.8"/>'
                )
    dots = [
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#00d2ff" fill-opacity="0.85"/>'
        for x, y, r in nodes
    ]
    view_box = f"0 0 {NETWORK_WIDTH} {NETWORK_HEIGHT}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" class="network" '
        f'preserveAspectRatio="xMidYMid slice">{"".join(lines)}{"".join(dots)}</svg>'
    )


@dataclass(frozen=True, slots=True)
class Novelty:
    """Qué trae de nuevo una corrida automática frente a la anterior (ADR-0034).

    En la auditoría del 27/10/2026, el 88 al 94 % de las notas de cada corrida
    ya venía en la anterior, cuando cada una cubría hoy y ayer. Desde el
    28/10/2026 cada corrida cubre solo su periodo (ADR-0031), pero un hecho
    que se siguió publicando ya se reportó en la anterior.

    Attributes:
        previous_at: Hora programada de la corrida anterior, si la tiene.
        new_facts: Hechos sin ninguna nota en la corrida anterior.
        known_facts: Hechos que ya venían.
        known_with_news: De los que ya venían, cuántos suman medios nuevos.
    """

    previous_at: datetime | None
    new_facts: int
    known_facts: int
    known_with_news: int


def novelty(articles: Sequence[ArticleItem], previous: PreviousRun) -> Novelty:
    """Cuenta los hechos nuevos y los ya reportados.

    Args:
        articles: Notas relevantes de la corrida.
        previous: La corrida anterior y sus notas.

    Returns:
        Los conteos para la sección «Novedades».
    """
    known = previous.article_ids
    stories = _stories(articles)
    was_known = [_is_known(story, known) for story in stories]
    with_news = [
        flag and any(a.article_id not in known for a in _members(story))
        for story, flag in zip(stories, was_known, strict=True)
    ]
    return Novelty(
        previous_at=previous.scheduled_for,
        new_facts=was_known.count(False),
        known_facts=was_known.count(True),
        known_with_news=with_news.count(True),
    )


@dataclass(frozen=True, slots=True)
class OraculoView:
    """Todo lo de Oráculo que la plantilla muestra.

    Attributes:
        code: Número de expediente.
        issued: Fecha de emisión en mayúsculas («26 OCT 2026»).
        automatic: Si viene de una corrida automática del monitor FGR.
        states_with_notes: Estados con al menos una nota.
        top_category: La categoría con más notas (sin contar «Otros»), o vacío.
        cards: Tarjetas por categoría.
        stacks: Barras apiladas por estado.
        timeline: Línea del tiempo.
        groups: Índice Estado ▸ Categoría ▸ Noticias, hasta
            ``MAX_LISTED_FACTS`` hechos. En una corrida automática, solo los
            hechos nuevos frente a la anterior.
        network: La red de nodos de la portada (SVG).
        novelty: Lo nuevo frente a la corrida anterior, o ``None`` si no hay
            con qué comparar.
        donut: La dona de las notas por categoría.
        highlights: Los hechos más importantes, para la cronología.
        omitted_facts: Hechos que no cupieron en el índice.
    """

    code: str
    issued: str
    automatic: bool
    states_with_notes: int
    top_category: str
    cards: tuple[CategoryCard, ...]
    stacks: tuple[StateStack, ...]
    timeline: Timeline
    groups: tuple[StateGroup, ...]
    network: str
    novelty: Novelty | None = None
    donut: tuple[DonutSlice, ...] = ()
    highlights: tuple[Highlight, ...] = ()
    omitted_facts: int = 0


def build_oraculo(
    search: SearchDetail,
    articles: Sequence[ArticleItem],
    generated_at: datetime | None = None,
    previous: PreviousRun | None = None,
) -> OraculoView:
    """Calcula las secciones de Oráculo del reporte.

    Args:
        search: La búsqueda.
        articles: Notas relevantes, de la más reciente a la más vieja.
        generated_at: Cuándo se generó (por defecto, ahora).
        previous: La corrida automática anterior, para separar lo nuevo.

    Returns:
        Las secciones listas para la plantilla.
    """
    code = expediente(search)
    cards = category_cards(articles)
    named = [c for c in cards if c.name not in {"Otros", NO_CATEGORY}]
    listed = new_facts_only(articles, previous.article_ids) if previous else list(articles)
    groups, omitted = limit_groups(state_groups(listed))
    return OraculoView(
        code=code,
        issued=date_caps(generated_at or datetime.now(UTC)),
        automatic=search.scheduled_for is not None,
        states_with_notes=len({state_code(a) for a in articles if state_code(a)}),
        top_category=named[0].name if named else "",
        cards=cards,
        stacks=state_stacks(articles),
        timeline=timeline(articles),
        groups=groups,
        network=network_svg(code),
        novelty=novelty(articles, previous) if previous else None,
        donut=donut(cards),
        highlights=highlights(listed),
        omitted_facts=omitted,
    )
