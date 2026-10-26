"""Textos y fechas en español que comparten el reporte y los datos (§15).

Lo usan ``render.py`` (HTML y PDF) y ``exports.py`` (CSV y GeoJSON), para
que una nota se describa igual en todos los formatos y en la pantalla.

No hace: no arma ningún documento.
"""

from datetime import date, datetime

from app.application.clock import MEXICO_CITY
from app.domain.aggregates import AggregateLevel

LEVEL_LABEL = {
    AggregateLevel.COUNTRY: "País",
    AggregateLevel.STATE: "Estado",
    AggregateLevel.MUNICIPALITY: "Municipio",
    AggregateLevel.LOCALITY: "Localidad",
}
# Mismas palabras que la leyenda de precisión del globo (§14.4).
PRECISION_LABEL = {
    "locality": "Localidad",
    "municipality": "Municipio",
    "state": "Solo estado",
    "country": "Solo país",
    "unknown": "Sin ubicación",
}
PROVIDER_LABEL = {
    "searchapi": "Google News (SearchApi)",
    "indice_local": "Índice local (GDELT y medios mexicanos)",
    "gdelt": "GDELT",
    "google_news_rss": "Google News RSS",
}
# Proveedores con datos de GDELT: piden citar "The GDELT Project" (§8).
GDELT_PROVIDERS = frozenset({"indice_local", "gdelt"})


def mexico_datetime(value: datetime | None) -> str:
    """Fecha y hora en la Ciudad de México ("16/10/2026 11:38").

    Args:
        value: Momento con zona horaria, o ``None``.

    Returns:
        El texto, o "Sin fecha".
    """
    if value is None:
        return "Sin fecha"
    return value.astimezone(MEXICO_CITY).strftime("%d/%m/%Y %H:%M")


def mexico_time(value: datetime | None) -> str:
    """Hora en la Ciudad de México ("07:00"), para la corrida programada.

    Args:
        value: Momento con zona horaria, o ``None``.

    Returns:
        El texto, o "sin hora".
    """
    if value is None:
        return "sin hora"
    return value.astimezone(MEXICO_CITY).strftime("%H:%M")


def provider_name(value: str) -> str:
    """Nombre de una fuente para el reporte ("Google News RSS").

    Args:
        value: Id de la fuente (``searches.providers``).

    Returns:
        El nombre, o el id si no se conoce.
    """
    return PROVIDER_LABEL.get(value, value)


def mexico_date(value: date) -> str:
    """Fecha corta ("16/10/2026").

    Args:
        value: Día.

    Returns:
        El texto.
    """
    return value.strftime("%d/%m/%Y")
