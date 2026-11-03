"""Constructor de consultas (``build_queries``, especificación §7.2).

Convierte un concepto, un lugar y un rango de fechas en las consultas que
se enviarían a cada proveedor. Lo usan "Probar concepto" (F2), que las
muestra sin gastar créditos, y el pipeline de búsqueda (F4), que las
ejecuta.

Regla de §7.2: **una consulta por proveedor y concepto**, con las palabras
clave unidas por OR. Si el texto excede el límite del proveedor, las
palabras clave se reparten en varias consultas, conservando el orden.

Excepción: un proveedor gratis con tope de notas por respuesta (Google News
RSS, 100) se parte por palabra clave y, en ventanas cortas, por día, sin
pasar de ``QueryDialect.split_up_to`` consultas. Con OR las palabras
compiten por las mismas 100 notas y la sigla «FGR» tapaba al nombre completo.

Con subdivisión (02/11/2026, «FGR + Homicidio»), cada consulta lleva un
segundo grupo con las palabras del tema, que también deben aparecer. Si ese
grupo no cabe en el límite del proveedor, se parte en varios y cada parte
lleva sus propias consultas.

No hace: no aplica el presupuesto por búsqueda (``MAX_QUERIES_PER_SEARCH``)
ni la caché; eso es de la búsqueda completa (F3/F4).
"""

from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from app.domain.errors import ConceptValidationError, QueryTooLongError
from app.domain.queries import (
    SEARCH_LANGUAGE,
    DateWindow,
    PlannedQuery,
    Provider,
    QueryPlace,
)
from app.domain.query_dialects import DIALECTS, QueryDialect

# Ventanas de fechas fijas de hasta tantos días se parten por día. Con más, las
# consultas no cabrían en el máximo por búsqueda (MAX_QUERIES_PER_SEARCH = 10).
SPLIT_MAX_DAYS = 3


class ConceptTerms(Protocol):
    """Lo que ``build_queries`` necesita de un concepto (guardado o borrador)."""

    @property
    def keywords(self) -> tuple[str, ...]:
        """Palabras clave."""
        ...

    @property
    def exclude_terms(self) -> tuple[str, ...]:
        """Exclusiones."""
        ...


def _split_keywords(
    dialect: QueryDialect,
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    topic: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    """Reparte las palabras clave en grupos que quepan en el límite del proveedor."""

    def fits(chunk: Sequence[str]) -> bool:
        return dialect.fits(dialect.render(chunk, place, concept.exclude_terms, window, topic))

    chunks: list[tuple[str, ...]] = []
    current: list[str] = []
    for keyword in concept.keywords:
        if fits([*current, keyword]):
            current.append(keyword)
            continue
        if not fits([keyword]):
            raise QueryTooLongError(
                f"La consulta para {dialect.label} no cabe en su límite ni con una sola "
                "palabra clave. Reduce las exclusiones o usa palabras más cortas.",
                {"proveedor": dialect.provider.value, "palabra": keyword},
            )
        chunks.append(tuple(current))
        current = [keyword]
    chunks.append(tuple(current))
    return chunks


def _days(window: DateWindow) -> list[DateWindow]:
    """Los días de una ventana fija corta, uno por uno; si no, la ventana entera.

    «Últimos N días» no se parte: ``when:Nd`` cuenta horas hacia atrás desde
    ahora y un día de calendario no equivale a eso.
    """
    span = (window.date_to - window.date_from).days + 1
    if window.relative_days is not None or not 1 < span <= SPLIT_MAX_DAYS:
        return [window]
    return [
        DateWindow.between(day, day)
        for day in (window.date_from + timedelta(days=i) for i in range(span))
    ]


def _split_topic(
    dialect: QueryDialect,
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    topic: tuple[str, ...],
) -> list[tuple[str, ...]]:
    """Reparte las palabras de la subdivisión en grupos que quepan con la palabra clave más larga.

    Sin subdivisión devuelve un solo grupo vacío, así el resto del plan no cambia.
    """
    if not topic:
        return [()]
    longest = max(concept.keywords, key=len)

    def fits(chunk: Sequence[str]) -> bool:
        return dialect.fits(
            dialect.render([longest], place, concept.exclude_terms, window, tuple(chunk))
        )

    chunks: list[tuple[str, ...]] = []
    current: list[str] = []
    for term in topic:
        if fits([*current, term]):
            current.append(term)
            continue
        if not current:
            raise QueryTooLongError(
                f"La consulta para {dialect.label} no cabe en su límite con la subdivisión. "
                "Usa palabras más cortas en la subdivisión o menos exclusiones.",
                {"proveedor": dialect.provider.value, "palabra": term},
            )
        chunks.append(tuple(current))
        current = [term]
    chunks.append(tuple(current))
    return chunks


def _plan(
    dialect: QueryDialect,
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    topic: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], DateWindow]]:
    """Qué palabras y qué días lleva cada consulta de un proveedor.

    Sin tope de notas, son los grupos de ``_split_keywords`` con la ventana
    completa. Con tope (``split_up_to``) se prueba, en este orden, lo que más
    notas trae sin pasarse: cada palabra cada día, cada grupo cada día, cada
    palabra con la ventana completa y, al final, los grupos.
    """
    chunks = _split_keywords(dialect, concept, place, window, topic)
    limit = dialect.split_up_to
    if limit is None:
        return [(chunk, window) for chunk in chunks]
    singles = [(keyword,) for keyword in concept.keywords]
    days = _days(window)
    for groups, spans in ((singles, days), (chunks, days), (singles, [window])):
        if len(groups) * len(spans) <= limit:
            return [(g, span) for g in groups for span in spans]
    return [(chunk, window) for chunk in chunks]


def build_queries(
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    providers: Sequence[Provider] = tuple(Provider),
    topic_terms: Sequence[str] = (),
) -> list[PlannedQuery]:
    """Genera las consultas que se enviarían a cada proveedor.

    Args:
        concept: Concepto con palabras clave y exclusiones.
        place: Cómo se nombra el lugar (``queries.place_for``).
        window: Rango de fechas.
        providers: Proveedores a usar, en orden (por defecto todos).
        topic_terms: Palabras de la subdivisión que también deben aparecer
            («FGR + Homicidio»); vacío para buscar solo el concepto.

    Returns:
        Una o más consultas por proveedor. Ninguna se ejecuta: sirven para
        mostrarlas y estimar créditos.

    Raises:
        ConceptValidationError: Si el concepto no tiene palabras clave.
        QueryTooLongError: Si ni una sola palabra clave cabe en el límite.

    Example:
        >>> [q.text for q in build_queries(ciberseguridad, iztapalapa, semana, [Provider.GDELT])]
        ['(ciberataque OR hackeo ...) Iztapalapa -curso ... sourcelang:spanish sourcecountry:MX']
    """
    if not concept.keywords:
        raise ConceptValidationError(
            "El concepto no tiene palabras clave.",
            {"problemas": [{"campo": "keywords", "mensaje": "Agrega al menos una palabra clave."}]},
        )
    topic = tuple(dict.fromkeys(topic_terms))
    queries = []
    for provider in providers:
        dialect = DIALECTS[provider]
        for topic_chunk in _split_topic(dialect, concept, place, window, topic):
            for chunk, span in _plan(dialect, concept, place, window, topic_chunk):
                queries.append(
                    PlannedQuery(
                        provider=provider,
                        # El texto lleva el día; ``window`` sigue siendo la
                        # ventana completa porque con ella el adaptador
                        # descarta lo de fuera (Google News RSS no siempre
                        # respeta after:/before:).
                        text=dialect.render(chunk, place, concept.exclude_terms, span, topic_chunk),
                        keywords=chunk,
                        country=place.country,
                        language=SEARCH_LANGUAGE,
                        window=window,
                        estimated_credits=dialect.credits_per_query,
                        exclude_terms=concept.exclude_terms,
                        place=place,
                        topic_terms=topic_chunk,
                    )
                )
    return queries
