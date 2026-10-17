"""Constructor de consultas (``build_queries``, especificación §7.2).

Convierte un concepto, un lugar y un rango de fechas en las consultas que
se enviarían a cada proveedor. Lo usan "Probar concepto" (F2), que las
muestra sin gastar créditos, y el pipeline de búsqueda (F4), que las
ejecuta.

Regla de §7.2: **una consulta por proveedor y concepto**, con las palabras
clave unidas por OR. Si el texto excede el límite del proveedor, las
palabras clave se reparten en varias consultas, conservando el orden.

No hace: no aplica el presupuesto por búsqueda (``MAX_QUERIES_PER_SEARCH``)
ni la caché; eso es de la búsqueda completa (F3/F4).
"""

from collections.abc import Sequence
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
    dialect: QueryDialect, concept: ConceptTerms, place: QueryPlace, window: DateWindow
) -> list[tuple[str, ...]]:
    """Reparte las palabras clave en grupos que quepan en el límite del proveedor."""

    def fits(chunk: Sequence[str]) -> bool:
        return dialect.fits(dialect.render(chunk, place, concept.exclude_terms, window))

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


def build_queries(
    concept: ConceptTerms,
    place: QueryPlace,
    window: DateWindow,
    providers: Sequence[Provider] = tuple(Provider),
) -> list[PlannedQuery]:
    """Genera las consultas que se enviarían a cada proveedor.

    Args:
        concept: Concepto con palabras clave y exclusiones.
        place: Cómo se nombra el lugar (``queries.place_for``).
        window: Rango de fechas.
        providers: Proveedores a usar, en orden (por defecto todos).

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
    queries = []
    for provider in providers:
        dialect = DIALECTS[provider]
        for chunk in _split_keywords(dialect, concept, place, window):
            queries.append(
                PlannedQuery(
                    provider=provider,
                    text=dialect.render(chunk, place, concept.exclude_terms, window),
                    keywords=chunk,
                    country=place.country,
                    language=SEARCH_LANGUAGE,
                    window=window,
                    estimated_credits=dialect.credits_per_query,
                    exclude_terms=concept.exclude_terms,
                    place=place,
                )
            )
    return queries
