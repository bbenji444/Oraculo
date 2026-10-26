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
- ``state_groups``: Estado ▸ Categoría ▸ Noticias, numeradas para citarlas.
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
from app.application.ports.search_reads import ArticleItem, SearchDetail
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
    """

    start: datetime
    label: str
    count: int
    share: float
    peak: bool


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
    every = _LABEL_EVERY[unit]
    bars = tuple(
        TimeBar(
            start=start,
            label=_axis_label(start, hourly) if index % every == 0 else "",
            count=len(buckets.get(start, [])),
            share=len(buckets.get(start, [])) / top,
            peak=start in peak_starts,
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
        groups: Estado ▸ Categoría ▸ Noticias.
        network: La red de nodos de la portada (SVG).
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


def build_oraculo(
    search: SearchDetail, articles: Sequence[ArticleItem], generated_at: datetime | None = None
) -> OraculoView:
    """Calcula las secciones de Oráculo del reporte.

    Args:
        search: La búsqueda.
        articles: Notas relevantes, de la más reciente a la más vieja.
        generated_at: Cuándo se generó (por defecto, ahora).

    Returns:
        Las secciones listas para la plantilla.
    """
    code = expediente(search)
    cards = category_cards(articles)
    named = [c for c in cards if c.name not in {"Otros", NO_CATEGORY}]
    return OraculoView(
        code=code,
        issued=date_caps(generated_at or datetime.now(UTC)),
        automatic=search.scheduled_for is not None,
        states_with_notes=len({state_code(a) for a in articles if state_code(a)}),
        top_category=named[0].name if named else "",
        cards=cards,
        stacks=state_stacks(articles),
        timeline=timeline(articles),
        groups=state_groups(articles),
        network=network_svg(code),
    )
