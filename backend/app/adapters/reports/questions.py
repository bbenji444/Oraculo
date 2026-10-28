"""Las preguntas del analista, respondidas con gráficas (rediseño del 28/10/2026).

Benji pidió ver el reporte «desde un punto humano»: quien lo lee es curioso,
preguntón y quiere todo claro y organizado. Cada sección del PDF responde una
pregunta con una representación visual y una línea de conclusión:

- ``top_facts``: ¿qué es lo más importante? (los hechos que más medios
  publicaron).
- ``actions``: ¿qué tipo de actuación hubo? (detenciones, aseguramientos,
  procesos, sentencias, investigaciones, denuncias).
- ``state_cards``: ¿qué pasa en cada estado?
- ``reliability``: ¿qué tan confiable es? (confianza de la IA y precisión
  del lugar).
- ``takeaways``: la conclusión de una línea de cada pregunta.

Todo se calcula de los datos guardados, sin IA y sin red. El tipo de
actuación sale del tipo de hecho que escribió la IA al leer la nota
(``event_type``) y del título, agrupados por palabras clave: es una
clasificación automática y así se rotula en el PDF.

No hace: no dibuja (eso es la plantilla) ni decide qué notas entran.
"""

import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.adapters.reports.oraculo import (
    NO_STATE,
    Badge,
    Segment,
    Timeline,
    badges,
    category_color,
    category_name,
    clean,
    confidence,
    ranked_stories,
    state_code,
    state_name,
)
from app.application.ports.search_reads import ArticleItem

PERCENT = 100
# Los 3 hechos de «¿Qué es lo más importante?»: los que caben como tarjetas
# grandes en la primera hoja de contenido.
TOP_FACTS = 3
# Fichas de «¿Qué pasa en cada estado?»: dos renglones de tres.
MAX_STATE_CARDS = 6
# Lo que no es una actuación reconocible (un asalto, un accidente).
OTHER_ACTION = "Otros hechos"

# Tipo de actuación, de la más específica a la más general: la primera regla
# que coincide gana. Se buscan en el tipo de hecho de la IA y en el título,
# en minúsculas y sin acentos. Medido con la corrida de las 07:00 del
# 28/10/2026: «denuncia», «detención», «investigación», «aseguramiento de
# hidrocarburo», «sentencia», «vinculación a proceso»…
ACTION_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Sentencias", "#7c5cd6", ("sentencia", "condena")),
    ("Procesos judiciales", "#3b82c4", ("vincul", "proceso", "imputa", "audiencia")),
    ("Detenciones", "#d6455d", ("detenc", "detien", "detenid", "captur", "aprehen", "arrest")),
    (
        "Aseguramientos y cateos",
        "#1aa37a",
        ("asegur", "decomis", "incaut", "cateo", "desmantel", "laboratorio"),
    ),
    ("Investigaciones", "#0090b8", ("investig", "indaga", "carpeta", "descarta", "deslind")),
    ("Denuncias", "#e0a100", ("denunci", "querella", "senalamiento", "acusa")),
)
OTHER_ACTION_COLOR = "#8a9aa3"


def _fold(text: str) -> str:
    """Minúsculas y sin acentos (la ñ queda como n: aquí solo se buscan raíces)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def action_of(article: ArticleItem) -> str:
    """El tipo de actuación de una nota, o «Otros hechos».

    Primero se mira el tipo de hecho que anotó la IA y, si no dice nada
    reconocible, el título. Con los dos juntos, «PAN exige a la FGR investigar
    a Taddei» (tipo de hecho: «denuncia») salía como investigación.

    Args:
        article: La nota.

    Returns:
        El nombre del grupo de ``ACTION_RULES`` que coincide primero.

    Example:
        >>> action_of(nota_con(event_type="vinculación a proceso"))
        'Procesos judiciales'
    """
    for text in (article.event_type or "", article.title):
        folded = _fold(text)
        for name, _, roots in ACTION_RULES:
            if any(root in folded for root in roots):
                return name
    return OTHER_ACTION


@dataclass(frozen=True, slots=True)
class Bar:
    """Una barra con nombre, color, conteo y largo respecto a la mayor.

    Attributes:
        name: Lo que cuenta.
        color: Su color.
        count: Notas.
        percent: Porcentaje del total.
        share: Largo respecto a la barra mayor (0 a 1).
    """

    name: str
    color: str
    count: int
    percent: int
    share: float


def _percent(count: int, total: int) -> int:
    return round(PERCENT * count / total) if total else 0


def actions(articles: Sequence[ArticleItem]) -> tuple[Bar, ...]:
    """¿Qué tipo de actuación hubo? Una barra por tipo, de más a menos notas.

    Args:
        articles: Notas relevantes.

    Returns:
        Las barras («Otros hechos» al final); vacío sin notas.
    """
    counts = Counter(action_of(a) for a in articles)
    colors = {name: color for name, color, _ in ACTION_RULES} | {OTHER_ACTION: OTHER_ACTION_COLOR}
    top = max(counts.values(), default=0)
    ranked = sorted(counts.items(), key=lambda item: (item[0] == OTHER_ACTION, -item[1], item[0]))
    return tuple(
        Bar(name, colors[name], count, _percent(count, len(articles)), count / top)
        for name, count in ranked
    )


@dataclass(frozen=True, slots=True)
class TopFact:
    """Un hecho de «¿Qué es lo más importante?».

    Attributes:
        rank: 1, 2 o 3.
        article: La primera nota del hecho.
        outlets: Cuántos medios lo publicaron.
        state: Estado.
        category: Categoría.
        color: Color de la categoría.
        action: Tipo de actuación.
        badges: Insignias (categoría, quién actúa, confianza).
    """

    rank: int
    article: ArticleItem
    outlets: int
    state: str
    category: str
    color: str
    action: str
    badges: tuple[Badge, ...]


def top_facts(articles: Sequence[ArticleItem], limit: int = TOP_FACTS) -> tuple[TopFact, ...]:
    """¿Qué es lo más importante? Los hechos que más medios publicaron.

    Args:
        articles: Notas relevantes.
        limit: Cuántos hechos.

    Returns:
        Del más publicado al menos publicado.
    """
    return tuple(
        TopFact(
            rank=index + 1,
            article=lead,
            outlets=1 + len(also),
            state=state_name(lead),
            category=category_name(lead),
            color=category_color(lead),
            action=action_of(lead),
            badges=badges(lead),
        )
        for index, (lead, also) in enumerate(ranked_stories(articles)[:limit])
    )


@dataclass(frozen=True, slots=True)
class StateCard:
    """Una ficha de «¿Qué pasa en cada estado?».

    Attributes:
        name: Estado.
        count: Notas.
        percent: Porcentaje de las notas relevantes.
        segments: Sus notas por categoría (barra apilada a lo ancho de la ficha).
        main_category: La categoría con más notas.
        main_action: El tipo de actuación con más notas.
        headline: Título del hecho que más medios publicaron en el estado.
    """

    name: str
    count: int
    percent: int
    segments: tuple[Segment, ...]
    main_category: str
    main_action: str
    headline: str


def state_cards(
    articles: Sequence[ArticleItem], limit: int = MAX_STATE_CARDS
) -> tuple[StateCard, ...]:
    """¿Qué pasa en cada estado? Una ficha por estado, de más a menos notas.

    Args:
        articles: Notas relevantes.
        limit: Cuántas fichas.

    Returns:
        Las fichas de los estados con notas (las notas sin estado no entran).
    """
    by_state: dict[str, list[ArticleItem]] = defaultdict(list)
    for article in articles:
        if state_code(article):
            by_state[state_name(article)].append(article)
    ranked = sorted(by_state.items(), key=lambda item: (-len(item[1]), item[0]))[:limit]
    cards = []
    for name, members in ranked:
        colors = {category_name(a): category_color(a) for a in members}
        counts = Counter(category_name(a) for a in members)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        segments = tuple(
            Segment(category, colors[category], count, count / len(members))
            for category, count in ordered
        )
        lead = ranked_stories(members)[0][0]
        cards.append(
            StateCard(
                name=name,
                count=len(members),
                percent=_percent(len(members), len(articles)),
                segments=segments,
                main_category=ordered[0][0],
                main_action=Counter(action_of(a) for a in members).most_common(1)[0][0],
                headline=clean(lead.title),
            )
        )
    return tuple(cards)


@dataclass(frozen=True, slots=True)
class Reliability:
    """¿Qué tan confiable es? Confianza de la IA y precisión del lugar.

    Attributes:
        confidence: Notas con confianza ALTA, MEDIA y BAJA (en ese orden).
        precision: Notas con lugar preciso, solo estado, solo país y sin
            ubicación (en ese orden).
        outlets: Medios distintos.
    """

    confidence: tuple[Bar, ...]
    precision: tuple[Bar, ...]
    outlets: int


CONFIDENCE_COLORS = (("ALTA", "#1aa37a"), ("MEDIA", "#e0a100"), ("BAJA", "#d6455d"))
PRECISION_GROUPS = (
    ("Lugar preciso", "#0369a1", ("municipality", "locality")),
    ("Solo estado", "#7fb6d9", ("state",)),
    ("Solo país", "#b45309", ("country",)),
)
NO_PLACE = ("Sin ubicación", "#94a3b8")


def _bars(counts: Sequence[tuple[str, str, int]], total: int) -> tuple[Bar, ...]:
    return tuple(
        Bar(name, color, count, _percent(count, total), count / total if total else 0.0)
        for name, color, count in counts
    )


def reliability(articles: Sequence[ArticleItem]) -> Reliability:
    """¿Qué tan confiable es? Reparto de la confianza y de la precisión.

    Args:
        articles: Notas relevantes.

    Returns:
        Los repartos; ``share`` es la parte del total (para barras apiladas).
    """
    total = len(articles)
    by_confidence = Counter(confidence(a) for a in articles)
    by_precision: Counter[str] = Counter()
    for article in articles:
        precision = article.primary.precision if article.primary else None
        group = next((name for name, _, levels in PRECISION_GROUPS if precision in levels), None)
        by_precision[group or NO_PLACE[0]] += 1
    outlets = {a.source_name or a.source_domain for a in articles} - {None}
    return Reliability(
        confidence=_bars(
            [(level, color, by_confidence[level]) for level, color in CONFIDENCE_COLORS], total
        ),
        precision=_bars(
            [(name, color, by_precision[name]) for name, color, _ in PRECISION_GROUPS]
            + [(NO_PLACE[0], NO_PLACE[1], by_precision[NO_PLACE[0]])],
            total,
        ),
        outlets=len(outlets),
    )


@dataclass(frozen=True, slots=True)
class Takeaways:
    """La conclusión de una línea de cada pregunta (vacía si no hay datos).

    Attributes:
        crimes: ¿De qué delitos se trata?
        actions: ¿Qué tipo de actuación hubo?
        places: ¿Dónde pasó?
        timing: ¿Cuándo pasó?
        trust: ¿Qué tan confiable es?
    """

    crimes: str = ""
    actions: str = ""
    places: str = ""
    timing: str = ""
    trust: str = ""


def takeaways(
    articles: Sequence[ArticleItem],
    action_bars: Sequence[Bar],
    cards: Sequence[StateCard],
    line: Timeline,
    trust: Reliability,
) -> Takeaways:
    """Escribe la conclusión de cada pregunta con los números ya calculados.

    Args:
        articles: Notas relevantes.
        action_bars: ``actions``.
        cards: ``state_cards``.
        line: La línea del tiempo (``oraculo.timeline``).
        trust: ``reliability``.

    Returns:
        Las frases, en español y sin IA.
    """
    total = len(articles)
    if not total:
        return Takeaways()
    named = Counter(category_name(a) for a in articles if category_name(a) not in {"Otros"})
    crimes = ""
    if named:
        name, count = named.most_common(1)[0]
        crimes = f"{name} concentra {_percent(count, total)} % de las notas ({count} de {total})."
    acted = [b for b in action_bars if b.name != OTHER_ACTION]
    actions_line = (
        f"Lo más reportado: {acted[0].name.lower()} ({acted[0].count} "
        f"{'nota' if acted[0].count == 1 else 'notas'})."
        if acted
        else ""
    )
    places = _places_line(cards)
    timing = (
        f"El momento con más notas fue {line.peaks[0].when.lower()}: {line.peaks[0].count}."
        if line.peaks
        else ""
    )
    high = trust.confidence[0].count
    trust_line = f"{high} de {total} notas con confianza alta; {trust.outlets} medios distintos."
    return Takeaways(crimes, actions_line, places, timing, trust_line)


def _notes(count: int) -> str:
    return f"{count} {'nota' if count == 1 else 'notas'}"


def _places_line(cards: Sequence[StateCard]) -> str:
    """La frase de «¿Dónde pasó?», p. ej. «Tamaulipas y Jalisco encabezan con 3 notas cada uno»."""
    if not cards:
        return ""
    lead = cards[0]
    tied = [c.name for c in cards if c.count == lead.count]
    if len(tied) == 1:
        return f"{lead.name} encabeza con {_notes(lead.count)} ({lead.percent} %)."
    names = ", ".join(tied[:-1]) + f" y {tied[-1]}"
    return f"{names} encabezan con {_notes(lead.count)} cada uno."


def no_state_share(articles: Sequence[ArticleItem]) -> int:
    """Porcentaje de notas sin estado identificado (aviso en «¿Dónde pasó?»)."""
    return _percent(sum(1 for a in articles if state_name(a) == NO_STATE), len(articles))


@dataclass(frozen=True, slots=True)
class QuestionsView:
    """Las respuestas que muestra el reporte, pregunta por pregunta.

    Attributes:
        top: ¿Qué es lo más importante?
        actions: ¿Qué tipo de actuación hubo?
        states: ¿Qué pasa en cada estado?
        trust: ¿Qué tan confiable es?
        lines: La conclusión de una línea de cada pregunta.
        no_state_percent: Notas sin estado identificado, en porcentaje.
    """

    top: tuple[TopFact, ...]
    actions: tuple[Bar, ...]
    states: tuple[StateCard, ...]
    trust: Reliability
    lines: Takeaways
    no_state_percent: int


def build_questions(articles: Sequence[ArticleItem], line: Timeline) -> QuestionsView:
    """Responde las preguntas del analista con las notas relevantes.

    Args:
        articles: Notas relevantes.
        line: La línea del tiempo ya calculada (``oraculo.timeline``).

    Returns:
        Las respuestas listas para la plantilla.
    """
    action_bars = actions(articles)
    cards = state_cards(articles)
    trust = reliability(articles)
    return QuestionsView(
        top=top_facts(articles),
        actions=action_bars,
        states=cards,
        trust=trust,
        lines=takeaways(articles, action_bars, cards, line, trust),
        no_state_percent=no_state_share(articles),
    )
