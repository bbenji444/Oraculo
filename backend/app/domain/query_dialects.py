"""Cómo escribe cada proveedor una consulta: su "dialecto" (ADR-0009).

Los tres proveedores entienden lo básico de la misma forma: frases entre
comillas, grupos ``(a OR b)`` y exclusiones con signo menos. Cambian los
filtros que van **dentro** del texto y los límites de largo:

- **SearchApi** (Google News): solo el texto base. País, idioma y fechas
  van como parámetros (``gl``, ``hl``, ``time_period``) en el adaptador (F3).
- **Google News RSS**: el texto base más el rango de fechas como operador
  (``when:7d``, o ``after:``/``before:`` con fechas fijas). Es gratis, así
  que no pasa por la caché, y se parte por palabra clave y por día porque
  cada respuesta trae a lo más 100 notas (``split_up_to``).
- **GDELT DOC 2.0**: el texto base más ``sourcelang:spanish`` y
  ``sourcecountry:<FIPS>``; las fechas van como parámetros (``timespan``).
- **Índice local** (ADR-0013): no es un buscador externo, así que su
  "consulta" se escribe en palabras para que el analista entienda qué se
  filtra. No tiene límite de largo y no pasa por la caché: el índice cambia
  cada 15 minutos y consultarlo no cuesta nada.

No hace: no conoce los parámetros HTTP de cada API ni llama a nadie; eso es
de los adaptadores de F3.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from app.domain.queries import DateWindow, Provider, QueryPlace

# VERIFICAR: ningún proveedor documenta un largo máximo de consulta. Google
# limita las búsquedas a 32 palabras (límite clásico de su buscador web); se
# aplica a los dos proveedores basados en Google y se calibra en F3 con una
# consulta real aprobada.
GOOGLE_MAX_WORDS = 32
# VERIFICAR: límite prudente para GDELT, que tampoco lo documenta (F3).
GDELT_MAX_CHARS = 400
# Según https://www.searchapi.io/pricing solo se cobran las búsquedas que
# responden 200, una por petición. Cada página es una petición: medido el
# 21/10/2026 con la cuenta (3 páginas = 3 créditos). Este es el costo de una
# página; el adaptador pide hasta SEARCHAPI_MAX_PAGES (ADR-0019). GDELT y
# Google News RSS son gratuitos.
SEARCHAPI_CREDITS_PER_QUERY = 1
FREE = 0
# Google News RSS devuelve a lo más 100 notas por consulta. Medido el
# 27/10/2026 con la ventana de dos días de la corrida FGR: «("Fiscalía General
# de la República" OR FGR)» llegó justo a 100; partida por palabra clave y por
# día fueron 4 consultas (100 + 100 + 68 + 53) con 281 notas distintas. Con 4,
# un concepto y los otros 5 proveedores caben en MAX_QUERIES_PER_SEARCH (10).
RSS_MAX_QUERIES_PER_CONCEPT = 4

_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]")


def quote(term: str) -> str:
    """Pone entre comillas una frase de varias palabras para buscarla exacta.

    Args:
        term: Palabra o frase.

    Returns:
        ``"filtración de datos"`` con comillas; ``hackeo`` tal cual.
    """
    return f'"{term}"' if " " in term else term


def group(terms: Sequence[str]) -> str:
    """Une términos con OR; un término solo va sin paréntesis.

    GDELT rechaza paréntesis que no rodeen un OR ("Parentheses may only be
    used around OR'd statements"). VERIFICAR en F3 con una consulta real.

    Args:
        terms: Términos del grupo (al menos uno).

    Returns:
        ``(a OR "b c")`` o ``a``.
    """
    parts = [quote(term) for term in terms]
    return parts[0] if len(parts) == 1 else f"({' OR '.join(parts)})"


def base_query(
    keywords: Sequence[str],
    place: QueryPlace,
    exclusions: Sequence[str],
    topic: Sequence[str] = (),
) -> list[str]:
    """Partes comunes a los tres proveedores, en orden.

    Args:
        keywords: Palabras clave de esta consulta.
        place: Cómo se nombra el lugar.
        exclusions: Términos de exclusión del concepto.
        topic: Palabras de la subdivisión, que también deben aparecer (un
            segundo grupo: los buscadores unen los grupos con «y»).

    Returns:
        Las partes del texto: palabras clave, subdivisión, lugar, estado y
        exclusiones. VERIFICAR en F3 que GDELT acepte varios bloques OR
        hermanos (su documentación solo prohíbe anidarlos).
    """
    parts = [group(keywords)]
    if topic:
        parts.append(group(topic))
    if place.terms:
        parts.append(group(place.terms))
    if place.required_terms:
        parts.append(group(place.required_terms))
    parts.extend(f"-{quote(term)}" for term in exclusions)
    return parts


def _no_suffix(place: QueryPlace, window: DateWindow) -> list[str]:
    return []


def _google_news_rss_suffix(place: QueryPlace, window: DateWindow) -> list[str]:
    # when:, after: y before: no son operadores documentados de Google News
    # RSS. Medido el 16/10/2026: when:7d sí limita a 7 días; after:/before:
    # NO se respetan (llegaron notas posteriores a before:), así que el
    # adaptador descarta lo que cae fuera del rango. Se envían igual porque
    # orientan la búsqueda. before: excluye su fecha: se usa el día siguiente.
    if window.relative_days is not None:
        return [f"when:{window.relative_days}d"]
    end = window.date_to + timedelta(days=1)
    return [f"after:{window.date_from.isoformat()}", f"before:{end.isoformat()}"]


def _web_date_suffix(place: QueryPlace, window: DateWindow) -> list[str]:
    # Búsqueda web de Google (BrowserWork → Google 2, ADR-0028): after: y
    # before: sí son operadores de Google web; before: excluye su fecha, así
    # que se usa el día siguiente. # VERIFICAR con la primera llamada real.
    end = window.date_to + timedelta(days=1)
    return [f"after:{window.date_from.isoformat()}", f"before:{end.isoformat()}"]


def gdelt_country(place: QueryPlace) -> str:
    """Valor de ``sourcecountry:`` para GDELT.

    Su documentación acepta el código FIPS o el nombre en inglés sin
    espacios; se prefiere el FIPS de Natural Earth (ADR-0009).

    Args:
        place: Lugar con su país.

    Returns:
        ``MX``, o ``norway`` si el país no tiene FIPS.
    """
    country = place.country
    return country.fips_code or _NOT_ALPHANUMERIC.sub("", country.name_en.lower())


def _gdelt_suffix(place: QueryPlace, window: DateWindow) -> list[str]:
    return ["sourcelang:spanish", f"sourcecountry:{gdelt_country(place)}"]


def _in_words(terms: Sequence[str]) -> str:
    """'a', 'a o b', 'a, b o "c d"'."""
    parts = [quote(term) for term in terms]
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} o {parts[-1]}"


def local_index_text(
    keywords: Sequence[str],
    place: QueryPlace,
    exclusions: Sequence[str],
    window: DateWindow,
    topic: Sequence[str] = (),
) -> str:
    """Describe en palabras lo que filtrará el índice local.

    Args:
        keywords: Palabras clave.
        place: Lugar.
        exclusions: Exclusiones.
        window: Rango (va aparte, en los filtros de la vista previa).
        topic: Palabras de la subdivisión, que también deben aparecer.

    Returns:
        Por ejemplo ``contiene: hackeo o ciberataque · lugar: Iztapalapa ·
        sin: curso``.
    """
    parts = [f"contiene: {_in_words(keywords)}"]
    if topic:
        parts.append(f"y también: {_in_words(topic)}")
    if place.terms:
        where = _in_words(place.terms)
        if place.required_terms:
            where += f" (y {_in_words(place.required_terms)})"
        parts.append(f"lugar: {where}")
    else:
        parts.append(f"lugar: {place.country.name}")
    if exclusions:
        parts.append(f"sin: {_in_words(exclusions)}")
    return " · ".join(parts)


@dataclass(frozen=True, slots=True)
class QueryDialect:
    """Reglas de escritura de un proveedor.

    Attributes:
        provider: Proveedor.
        label: Nombre para mostrar.
        credits_per_query: Créditos estimados por consulta.
        max_words: Máximo de palabras del texto, o ``None``.
        max_chars: Máximo de caracteres del texto, o ``None``.
        suffix: Filtros que van al final del texto.
        cacheable: Si sus respuestas se guardan en la caché de consultas.
        split_up_to: Si sus respuestas tienen tope, cuántas consultas puede
            usar un concepto al partirse por palabra clave y por día
            (``None``: las palabras van juntas con OR, ver ``query_builder``).
        writer: Escritura propia del texto completo, en lugar del texto
            base más ``suffix`` (la usa el índice local).
    """

    provider: Provider
    label: str
    credits_per_query: int
    max_words: int | None
    max_chars: int | None
    suffix: Callable[[QueryPlace, DateWindow], list[str]]
    cacheable: bool = True
    split_up_to: int | None = None
    writer: (
        Callable[[Sequence[str], QueryPlace, Sequence[str], DateWindow, Sequence[str]], str] | None
    ) = None

    def render(
        self,
        keywords: Sequence[str],
        place: QueryPlace,
        exclusions: Sequence[str],
        window: DateWindow,
        topic: Sequence[str] = (),
    ) -> str:
        """Escribe el texto completo de una consulta.

        Args:
            keywords: Palabras clave de esta consulta.
            place: Cómo se nombra el lugar.
            exclusions: Términos de exclusión.
            window: Rango de fechas.
            topic: Palabras de la subdivisión, que también deben aparecer.

        Returns:
            El texto exacto que se enviará.
        """
        if self.writer is not None:
            return self.writer(keywords, place, exclusions, window, topic)
        return " ".join(
            [*base_query(keywords, place, exclusions, topic), *self.suffix(place, window)]
        )

    def fits(self, text: str) -> bool:
        """Dice si el texto cabe en los límites del proveedor.

        Las palabras se cuentan separando por espacios, incluidos ``OR`` y
        los filtros: es la cuenta más conservadora.

        Args:
            text: Texto de la consulta.

        Returns:
            ``True`` si cabe.
        """
        if self.max_words is not None and len(text.split()) > self.max_words:
            return False
        return self.max_chars is None or len(text) <= self.max_chars


DIALECTS: dict[Provider, QueryDialect] = {
    Provider.SEARCHAPI: QueryDialect(
        Provider.SEARCHAPI,
        "SearchApi (Google News)",
        SEARCHAPI_CREDITS_PER_QUERY,
        GOOGLE_MAX_WORDS,
        None,
        _no_suffix,
    ),
    Provider.GOOGLE_NEWS_RSS: QueryDialect(
        Provider.GOOGLE_NEWS_RSS,
        "Google News RSS",
        FREE,
        GOOGLE_MAX_WORDS,
        None,
        _google_news_rss_suffix,
        # Gratis: la caché solo lo volvía viejo. Medido el 27/10/2026: las
        # corridas de las 07:00 y las 15:00 reusaron la respuesta de las 03:45
        # y de las 11:29 (caché de 6 h) y no vieron lo publicado entre tanto.
        cacheable=False,
        split_up_to=RSS_MAX_QUERIES_PER_CONCEPT,
    ),
    Provider.GDELT: QueryDialect(
        Provider.GDELT, "GDELT", FREE, None, GDELT_MAX_CHARS, _gdelt_suffix
    ),
    # Bing no tiene operador de fecha en el texto: la ventana no se aplica y
    # la IA marca la fecha del hecho (ADR-0028).
    Provider.BROWSERWORK_BING: QueryDialect(
        Provider.BROWSERWORK_BING, "Bing (BrowserWork)", FREE, GOOGLE_MAX_WORDS, None, _no_suffix
    ),
    Provider.BROWSERWORK_GOOGLE2: QueryDialect(
        Provider.BROWSERWORK_GOOGLE2,
        "Google 2 (BrowserWork)",
        FREE,
        GOOGLE_MAX_WORDS,
        None,
        _web_date_suffix,
    ),
    Provider.LOCAL_INDEX: QueryDialect(
        Provider.LOCAL_INDEX,
        "Índice local (GDELT + medios)",
        FREE,
        None,
        None,
        _no_suffix,
        cacheable=False,
        writer=local_index_text,
    ),
}
