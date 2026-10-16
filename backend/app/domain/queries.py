"""Piezas de una consulta de noticias: proveedor, fechas, lugar y resultado.

Una búsqueda combina conceptos, una región y un rango de fechas. Aquí están
los tipos que describen esa combinación ya resuelta y la regla de qué
palabras nombran al lugar (ADR-0009):

- Se busca con los ``search_terms`` curados de la región o, si no tiene,
  con su nombre oficial.
- Un municipio cuyo nombre se repite en otro estado lleva también los
  términos de su estado ("Benito Juárez" existe en 7 estados). Las
  localidades siempre lo llevan.
- Un país no agrega lugar al texto: se filtra con el país del proveedor.

El texto exacto de cada proveedor lo arma ``app.domain.query_dialects`` y
``app.domain.query_builder.build_queries`` junta todo.

No hace: no consulta la base (recibe los datos del lugar ya leídos) ni llama
a ningún proveedor.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from enum import StrEnum

from app.domain.errors import InvalidRequestError
from app.domain.region import RegionLevel

# GDELT solo cubre los últimos 3 meses (documentación de DOC 2.0); una
# ventana mayor daría resultados incompletos sin avisar.
MAX_WINDOW_DAYS = 90
# El sistema monitorea prensa en español (ADR-0009).
SEARCH_LANGUAGE = "es"
SEARCH_LANGUAGE_LABEL = "español"
_DATE_FORMAT = "%d/%m/%Y"


class Provider(StrEnum):
    """Proveedores de noticias (especificación §8), en el orden en que se muestran."""

    SEARCHAPI = "searchapi"
    GOOGLE_NEWS_RSS = "google_news_rss"
    GDELT = "gdelt"


@dataclass(frozen=True, slots=True)
class DateWindow:
    """Rango de fechas de una búsqueda.

    Attributes:
        date_from: Primer día (en hora de la Ciudad de México).
        date_to: Último día, incluido.
        relative_days: ``7`` si se pidió "últimos 7 días"; ``None`` si es un
            rango con fechas fijas. Los proveedores lo expresan distinto.
    """

    date_from: date
    date_to: date
    relative_days: int | None

    @classmethod
    def last_days(cls, days: int, today: date) -> "DateWindow":
        """Ventana de los últimos ``days`` días hasta hoy.

        Args:
            days: Días hacia atrás (1 a 90).
            today: Fecha de hoy en la Ciudad de México.

        Returns:
            La ventana.

        Raises:
            InvalidRequestError: Si ``days`` está fuera de rango.
        """
        if not 1 <= days <= MAX_WINDOW_DAYS:
            raise InvalidRequestError(
                f"El rango debe ser de 1 a {MAX_WINDOW_DAYS} días "
                "(GDELT solo cubre los últimos 3 meses).",
                {"days": days},
            )
        return cls(today - timedelta(days=days), today, days)

    @classmethod
    def between(cls, date_from: date, date_to: date) -> "DateWindow":
        """Ventana con fechas fijas, ambos días incluidos.

        Args:
            date_from: Primer día.
            date_to: Último día.

        Returns:
            La ventana.

        Raises:
            InvalidRequestError: Si las fechas están al revés o el rango
                pasa de 90 días.
        """
        if date_to < date_from:
            raise InvalidRequestError(
                "La fecha final es anterior a la inicial.",
                {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            )
        if (date_to - date_from).days + 1 > MAX_WINDOW_DAYS:
            raise InvalidRequestError(
                f"El rango puede abarcar hasta {MAX_WINDOW_DAYS} días.",
                {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            )
        return cls(date_from, date_to, None)

    def contains(self, moment: datetime, tz: tzinfo) -> bool:
        """Dice si un momento cae dentro del rango (días contados en ``tz``).

        Sirve para descartar notas que un proveedor devuelve fuera del rango
        pedido: Google News RSS ignora ``after:``/``before:`` (medido el
        16/10/2026: 4 de 38 notas fuera de un rango fijo).

        Args:
            moment: Fecha y hora con zona.
            tz: Zona en que se cuentan los días (la de la Ciudad de México).

        Returns:
            ``True`` si su día local está entre ``date_from`` y ``date_to``.
        """
        return self.date_from <= moment.astimezone(tz).date() <= self.date_to

    def describe(self) -> str:
        """Descripción para la persona: "últimos 7 días" o "del 01/10/2026 al 15/10/2026"."""
        if self.relative_days == 1:
            return "último día"
        if self.relative_days is not None:
            return f"últimos {self.relative_days} días"
        return f"del {self.date_from:{_DATE_FORMAT}} al {self.date_to:{_DATE_FORMAT}}"


@dataclass(frozen=True, slots=True)
class CountryFilter:
    """País por el que filtran los proveedores.

    Attributes:
        name: Nombre en español, para mostrar.
        iso_a2: Código ISO de 2 letras (SearchApi, Google News RSS).
        fips_code: Código FIPS (GDELT), si existe.
        name_en: Nombre en inglés (respaldo de GDELT sin FIPS).
    """

    name: str
    iso_a2: str | None
    fips_code: str | None
    name_en: str


@dataclass(frozen=True, slots=True)
class PlaceFacts:
    """Datos de la región elegida que importan para armar la consulta.

    Los lee el repositorio de regiones; la regla de qué hacer con ellos está
    en ``place_for``.

    Attributes:
        level: Nivel de la región.
        name: Nombre oficial.
        search_terms: Términos curados (vacío = usar ``name``).
        name_is_repeated: Si otra región del mismo nivel se llama igual.
        state_name: Nombre del estado que la contiene (``None`` en países y
            estados).
        state_search_terms: Términos curados de ese estado.
        country: País de la región.
    """

    level: RegionLevel
    name: str
    search_terms: tuple[str, ...]
    name_is_repeated: bool
    state_name: str | None
    state_search_terms: tuple[str, ...]
    country: CountryFilter


@dataclass(frozen=True, slots=True)
class QueryPlace:
    """Cómo se nombra el lugar dentro de la consulta.

    Attributes:
        terms: Palabras del lugar (se unen con OR). Vacío en un país.
        required_terms: Palabras del estado que también deben aparecer, para
            distinguir nombres repetidos. Vacío si no hace falta.
        country: País por el que filtran los proveedores.
    """

    terms: tuple[str, ...]
    required_terms: tuple[str, ...]
    country: CountryFilter


def place_for(facts: PlaceFacts) -> QueryPlace:
    """Decide qué palabras nombran al lugar en la consulta (ADR-0009).

    Args:
        facts: Datos de la región elegida.

    Returns:
        El lugar listo para armar consultas.

    Example:
        >>> place_for(benito_juarez_quintana_roo).required_terms
        ('Quintana Roo',)
    """
    if facts.level is RegionLevel.COUNTRY:
        return QueryPlace((), (), facts.country)
    terms = facts.search_terms or (facts.name,)
    needs_state = facts.level is RegionLevel.LOCALITY or (
        facts.level is RegionLevel.MUNICIPALITY and facts.name_is_repeated
    )
    required: tuple[str, ...] = ()
    if needs_state and facts.state_name is not None:
        required = facts.state_search_terms or (facts.state_name,)
    return QueryPlace(terms, required, facts.country)


@dataclass(frozen=True, slots=True)
class PlannedQuery:
    """Una consulta lista para enviarse a un proveedor (todavía no se envía).

    Attributes:
        provider: Proveedor destino.
        text: Texto exacto de la consulta.
        keywords: Palabras clave que cubre (puede ser parte del concepto si
            la consulta se partió por largo).
        country: País por el que se filtra.
        language: Idioma (``es``).
        window: Rango de fechas.
        estimated_credits: Créditos que se espera gastar.
    """

    provider: Provider
    text: str
    keywords: tuple[str, ...]
    country: CountryFilter
    language: str
    window: DateWindow
    estimated_credits: int
