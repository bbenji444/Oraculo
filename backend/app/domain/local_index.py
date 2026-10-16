"""Qué notas del índice local responden a una consulta (ADR-0013).

Convierte una ``PlannedQuery`` en criterios concretos que el adaptador de
``indice_local`` traduce a SQL:

- **Palabras clave:** al menos una aparece como palabra completa en el
  título o el fragmento (``text_norm``), comparando con la misma
  normalización del catálogo (mayúsculas, sin acentos, con Ñ).
- **Exclusiones:** si aparece alguna, la nota se descarta.
- **Lugar:** algún término del lugar aparece en el texto (y, si hace falta
  para distinguir nombres repetidos, también el estado), **o** la región es
  un estado y GDELT ubicó la nota ahí. En México a nivel país no se filtra
  por lugar: todo el índice es de México. En otro país se pide su nombre.
- **Fechas:** días completos en la zona de la Ciudad de México.
- **Tope:** las ``MAX_LOCAL_RESULTS`` más recientes.

No hace: no consulta la base ni sabe de SQL.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo

from app.domain.errors import InvalidRequestError
from app.domain.names import normalize_name
from app.domain.queries import PlannedQuery, QueryPlace

# Mismo máximo que una consulta de GDELT DOC (maxrecords=250): ningún
# proveedor entrega más por consulta y así se comparan igual.
MAX_LOCAL_RESULTS = 250
# El índice solo guarda notas sobre México (filtro de la ingesta).
INDEX_COUNTRY_ISO = "MX"


@dataclass(frozen=True, slots=True)
class LocalIndexCriteria:
    """Criterios de búsqueda en el índice local, ya normalizados.

    Attributes:
        keywords: Al menos una debe aparecer.
        exclusions: Ninguna debe aparecer.
        place_terms: Al menos uno debe aparecer; vacío = sin filtro de lugar.
        required_terms: Si no está vacío, también debe aparecer uno.
        state_code: Clave INEGI: una nota que GDELT ubicó en ese estado
            cumple el lugar aunque el texto no lo nombre.
        start: Primer instante incluido (UTC).
        end: Primer instante ya no incluido (UTC).
        limit: Máximo de notas.
    """

    keywords: tuple[str, ...]
    exclusions: tuple[str, ...]
    place_terms: tuple[str, ...]
    required_terms: tuple[str, ...]
    state_code: str | None
    start: datetime
    end: datetime
    limit: int = MAX_LOCAL_RESULTS


def _normalized(terms: tuple[str, ...]) -> tuple[str, ...]:
    clean = (normalize_name(term) for term in terms)
    return tuple(dict.fromkeys(term for term in clean if term))


def criteria_for(query: PlannedQuery, tz: tzinfo) -> LocalIndexCriteria:
    """Traduce una consulta planeada a criterios del índice local.

    Args:
        query: Consulta de ``build_queries``.
        tz: Zona en que se cuentan los días (la de la Ciudad de México).

    Returns:
        Los criterios.

    Raises:
        InvalidRequestError: Si no queda ninguna palabra clave.

    Example:
        >>> criteria_for(hackeo_en_iztapalapa_hoy, MEXICO_CITY).place_terms
        ('IZTAPALAPA',)
    """
    keywords = _normalized(query.keywords)
    if not keywords:
        raise InvalidRequestError("La consulta no tiene palabras clave.")
    place = query.place or QueryPlace((), (), query.country)
    place_terms = _normalized(place.terms)
    if not place_terms and place.country.iso_a2 != INDEX_COUNTRY_ISO:
        place_terms = _normalized((place.country.name,))
    window = query.window
    start = datetime.combine(window.date_from, time.min, tzinfo=tz)
    end = datetime.combine(window.date_to + timedelta(days=1), time.min, tzinfo=tz)
    return LocalIndexCriteria(
        keywords=keywords,
        exclusions=_normalized(query.exclude_terms),
        place_terms=place_terms,
        required_terms=_normalized(place.required_terms),
        state_code=place.state_code,
        start=start.astimezone(UTC),
        end=end.astimezone(UTC),
    )
