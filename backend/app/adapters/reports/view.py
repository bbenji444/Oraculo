"""Cifras, gráficas y agrupaciones que muestra el reporte (especificación §15).

Todo se calcula de los datos de la búsqueda, sin IA: los "datos clave" de la
portada, las notas por día, los medios con más notas, las barras de la tabla
por subregión y las notas agrupadas en "dentro", "fuera" y "sin ubicación",
numeradas para citarlas.

Lo usa ``render.py`` para llenar la plantilla. Las fechas se cuentan en la
Ciudad de México (CLAUDE.md §6.3).

No hace: no dibuja HTML ni decide qué notas van (eso es ``BuildReport``).
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.adapters.reports.labels import GDELT_PROVIDERS, LEVEL_LABEL
from app.adapters.reports.oraculo import OraculoView, build_oraculo
from app.adapters.reports.static_map import LegendClass, legend
from app.application.clock import MEXICO_CITY
from app.application.ports.search_reads import ArticleItem
from app.application.use_cases.reports import ReportData

# Medios en la gráfica de la portada: más ya no se leen en media página.
MAX_SOURCES = 5
# Filas de la tabla por subregión: el resto se suma en "Otros" (Oaxaca tiene
# 570 municipios y la tabla debe caber junto al mapa).
MAX_SUBREGION_ROWS = 12
# Plural del nivel para "Otros 5 municipios".
LEVEL_PLURAL = {
    "País": "países",
    "Estado": "estados",
    "Municipio": "municipios",
    "Localidad": "localidades",
}
# Hasta un mes se dibuja una barra por día; más largo, una por semana.
MAX_DAY_BARS = 31
DAYS_PER_WEEK = 7
WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
PERCENT = 100


@dataclass(frozen=True, slots=True)
class Bar:
    """Una barra de una gráfica.

    Attributes:
        label: Texto principal ("14/10", "Guadalajara").
        detail: Texto secundario ("mar"), o vacío.
        count: Notas.
        share: Largo de la barra de 0 a 1 (respecto a la más grande).
        percent: Porcentaje del total de notas relevantes, redondeado.
    """

    label: str
    detail: str
    count: int
    share: float
    percent: int


@dataclass(frozen=True, slots=True)
class Fact:
    """Un dato clave de la portada.

    Attributes:
        label: Qué es ("Día con más notas").
        value: El dato ("14/10/2026").
        note: Aclaración corta ("8 notas"), o vacío.
    """

    label: str
    value: str
    note: str


@dataclass(frozen=True, slots=True)
class NumberedArticle:
    """Una nota con su número de cita en el reporte.

    Attributes:
        number: Número corrido en todo el reporte (1, 2, 3...).
        article: La nota.
    """

    number: int
    article: ArticleItem


@dataclass(frozen=True, slots=True)
class NewsGroup:
    """Notas de un mismo grupo.

    Attributes:
        key: ``inside``, ``outside`` o ``unlocated`` (para el estilo).
        title: Título de la sección.
        articles: Sus notas numeradas, de la más reciente a la más vieja.
    """

    key: str
    title: str
    articles: tuple[NumberedArticle, ...]


@dataclass(frozen=True, slots=True)
class ReportView:
    """Lo que la plantilla muestra además de ``ReportData``.

    Attributes:
        title: Conceptos de la búsqueda ("Extorsión, Secuestro").
        level_label: Nivel de las subregiones ("Municipio").
        total: Notas relevantes.
        inside: Notas dentro de la región.
        inside_percent: Porcentaje dentro de la región.
        facts: Datos clave de la portada.
        subregions: Barras de la tabla por subregión (las de más notas).
        other_subregions: Subregiones con notas que no caben en la tabla.
        level_plural: Nivel en plural, en minúsculas ("municipios").
        other_notes: Sus notas.
        days: Barras de notas por día (o por semana).
        days_unit: "día" o "semana".
        undated: Notas sin fecha de publicación (no van en la gráfica).
        sources: Barras de los medios con más notas.
        groups: Notas agrupadas y numeradas (solo los grupos con notas).
        legend: Colores del mapa.
        uses_gdelt: Si hay que citar a The GDELT Project (§8).
        oraculo: Expediente, categorías, línea del tiempo y Estado ▸ Categoría
            ▸ Noticias (F12.10, ADR-0033).
    """

    title: str
    level_label: str
    total: int
    inside: int
    inside_percent: int
    facts: tuple[Fact, ...]
    subregions: tuple[Bar, ...]
    other_subregions: int
    level_plural: str
    other_notes: int
    days: tuple[Bar, ...]
    days_unit: str
    undated: int
    sources: tuple[Bar, ...]
    groups: tuple[NewsGroup, ...]
    legend: tuple[LegendClass, ...]
    uses_gdelt: bool
    oraculo: OraculoView


def _percent(count: int, total: int) -> int:
    return round(PERCENT * count / total) if total else 0


def _bars(items: Sequence[tuple[str, str, int]], total: int) -> tuple[Bar, ...]:
    top = max((count for _, _, count in items), default=0)
    return tuple(
        Bar(label, detail, count, count / top if top else 0, _percent(count, total))
        for label, detail, count in items
    )


def _local_day(article: ArticleItem) -> date | None:
    if article.published_at is None:
        return None
    return article.published_at.astimezone(MEXICO_CITY).date()


def day_bars(
    articles: Sequence[ArticleItem], date_from: date, date_to: date
) -> tuple[tuple[Bar, ...], str]:
    """Notas por día del periodo buscado, con los días sin notas en cero.

    Args:
        articles: Notas relevantes.
        date_from: Primer día de la búsqueda.
        date_to: Último día.

    Returns:
        Una barra por día ("14/10", "mar"), o por semana si el periodo pasa
        de un mes, y la unidad ("día" o "semana"). Las notas publicadas fuera
        del periodo se suman al día más cercano.
    """
    counts: Counter[date] = Counter()
    for article in articles:
        day = _local_day(article)
        if day is not None:
            counts[min(max(day, date_from), date_to)] += 1
    total = len(articles)
    span = (date_to - date_from).days + 1
    if span <= MAX_DAY_BARS:
        days = [date_from + timedelta(days=i) for i in range(span)]
        items = [(d.strftime("%d/%m"), WEEKDAYS[d.weekday()], counts[d]) for d in days]
        return _bars(items, total), "día"
    weeks: list[tuple[str, str, int]] = []
    for start in range(0, span, DAYS_PER_WEEK):
        first = date_from + timedelta(days=start)
        last = min(first + timedelta(days=DAYS_PER_WEEK - 1), date_to)
        count = sum(counts[first + timedelta(days=i)] for i in range((last - first).days + 1))
        weeks.append((first.strftime("%d/%m"), f"al {last.strftime('%d/%m')}", count))
    return _bars(weeks, total), "semana"


def source_bars(articles: Sequence[ArticleItem]) -> tuple[Bar, ...]:
    """Los medios con más notas relevantes.

    Args:
        articles: Notas relevantes.

    Returns:
        Hasta ``MAX_SOURCES`` barras, de más a menos (empates por nombre).
        Un medio cuenta una vez aunque unas notas traigan su nombre ("La
        Silla Rota") y otras solo su dominio ("lasillarota.com"): se agrupan
        por dominio y se muestra el nombre si alguna nota lo trae.
    """
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    for article in articles:
        key = article.source_domain or article.source_name or "Medio sin nombre"
        counts[key] += 1
        if article.source_name:
            names.setdefault(key, article.source_name)
    labeled = [(names.get(key, key), count) for key, count in counts.items()]
    top = sorted(labeled, key=lambda item: (-item[1], item[0]))[:MAX_SOURCES]
    return _bars([(name, "", count) for name, count in top], len(articles))


def news_groups(articles: Sequence[ArticleItem], region: str) -> tuple[NewsGroup, ...]:
    """Agrupa las notas como las pestañas de la pantalla y las numera.

    Args:
        articles: Notas relevantes, de la más reciente a la más vieja.
        region: Nombre de la región para los títulos ("Jalisco").

    Returns:
        "En {región}", "Fuera de {región}" y "Sin ubicación", en ese orden,
        solo los que tienen notas. La numeración sigue de un grupo al otro.
    """
    plan = (
        ("inside", f"En {region}", True),
        ("outside", f"Fuera de {region}", False),
        ("unlocated", "Sin ubicación", None),
    )
    groups = []
    number = 0
    for key, title, in_region in plan:
        members = []
        for article in articles:
            if article.in_region is in_region:
                number += 1
                members.append(NumberedArticle(number, article))
        if members:
            groups.append(NewsGroup(key, title, tuple(members)))
    return tuple(groups)


def _facts(
    data: ReportData,
    level_label: str,
    days: tuple[Bar, ...],
    unit: str,
    sources: tuple[Bar, ...],
) -> tuple[Fact, ...]:
    total = len(data.articles)
    facts = []
    if data.counts:
        top = data.counts[0]
        facts.append(Fact(f"{level_label} con más notas", top.name, _notes(top.count)))
    busiest = max(days, key=lambda bar: bar.count, default=None)
    if busiest and busiest.count:
        if unit == "día":
            facts.append(
                Fact(
                    "Día con más notas", f"{busiest.detail} {busiest.label}", _notes(busiest.count)
                )
            )
        else:
            facts.append(
                Fact(
                    "Semana con más notas",
                    f"{busiest.label} {busiest.detail}",
                    _notes(busiest.count),
                )
            )
    if sources:
        facts.append(Fact("Medio con más notas", sources[0].label, _notes(sources[0].count)))
    inside = sum(c.count for c in data.counts) + data.coarser
    facts.append(
        Fact("Dentro de la región", f"{_percent(inside, total)} %", f"{inside} de {total} notas")
    )
    return tuple(facts)


def _notes(count: int) -> str:
    return "1 nota" if count == 1 else f"{count} notas"


def build_view(data: ReportData) -> ReportView:
    """Calcula todo lo que la plantilla muestra además de los datos.

    Args:
        data: Lo que lleva el reporte.

    Returns:
        Cifras, gráficas y grupos listos para la plantilla.
    """
    articles = data.articles
    total = len(articles)
    level_label = LEVEL_LABEL[data.level]
    inside = sum(c.count for c in data.counts) + data.coarser
    days, unit = day_bars(articles, data.search.date_from, data.search.date_to)
    sources = source_bars(articles)
    return ReportView(
        title=", ".join(c.name for c in data.search.concepts),
        level_label=level_label,
        total=total,
        inside=inside,
        inside_percent=_percent(inside, total),
        facts=_facts(data, level_label, days, unit, sources),
        subregions=_bars([(c.name, "", c.count) for c in data.counts[:MAX_SUBREGION_ROWS]], total),
        other_subregions=len(data.counts[MAX_SUBREGION_ROWS:]),
        level_plural=LEVEL_PLURAL[level_label],
        other_notes=sum(c.count for c in data.counts[MAX_SUBREGION_ROWS:]),
        days=days,
        days_unit=unit,
        undated=sum(1 for a in articles if a.published_at is None),
        sources=sources,
        groups=news_groups(articles, data.region.name),
        legend=tuple(legend(max((c.count for c in data.counts), default=0))),
        uses_gdelt=any(p.provider in GDELT_PROVIDERS and p.queries > 0 for p in data.providers),
        oraculo=build_oraculo(data.search, articles, data.generated_at),
    )
