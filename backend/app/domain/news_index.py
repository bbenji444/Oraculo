"""Nota del índice local (ADR-0013): lo que la ingesta guarda y en qué se busca.

Una ``NewsItem`` es la versión mínima de una nota: metadatos y link, nunca el
texto completo (CLAUDE.md §8). La ingesta la arma desde un archivo GKG de
GDELT o desde un RSS de un medio; el proveedor ``indice_local`` busca sobre
``text_norm`` (título + fragmento normalizados, conservando la Ñ).

Reglas de qué se guarda de GDELT: notas **en español** con **alguna
ubicación en México**. Las ubicaciones de GDELT se guardan solo como pistas
(``gdelt_states``): en la muestra real tenían errores, y la ubicación final la
decide F4 con el catálogo INEGI.

No hace: no lee formatos de archivo ni consulta la base.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.domain.articles import domain_of
from app.domain.names import normalize_name

# Código de idioma de GDELT para el español (campo TranslationInfo, srclc:spa).
SPANISH = "spa"
# Código de país de México en las ubicaciones de GDELT (FIPS 10-4).
MEXICO_FIPS = "MX"
GDELT_SOURCE = "gdelt_gkg"
RSS_SOURCE_PREFIX = "rss:"
_WEB_SCHEMES = frozenset({"http", "https"})


class InvalidNewsError(ValueError):
    """Una nota no se puede guardar (sin URL web, sin título o sin fecha)."""


@dataclass(frozen=True, slots=True)
class GdeltLocation:
    """Una ubicación tal como la reporta GDELT (pista, no ubicación final).

    Attributes:
        kind: Tipo de GDELT (1 país, 2 estado, 3 y 4 ciudad).
        name: Nombre completo ("Saltillo, Coahuila De Zaragoza, Mexico").
        country: Código FIPS del país ("MX").
        adm1: Código FIPS del estado ("MX07"), vacío si es el país.
        lat: Latitud, si viene.
        lon: Longitud, si viene.
    """

    kind: int
    name: str
    country: str
    adm1: str
    lat: float | None
    lon: float | None


@dataclass(frozen=True, slots=True)
class NewsItem:
    """Una nota lista para el índice local.

    Attributes:
        source: ``gdelt_gkg`` o ``rss:<medio>``.
        url: Link a la nota.
        title: Título limpio.
        snippet: Fragmento, si la fuente lo trae.
        source_name: Nombre del medio.
        source_domain: Dominio del medio.
        published_at: Fecha (UTC).
        language: Idioma que reporta la fuente.
        gdelt_states: Claves INEGI de los estados donde GDELT la ubicó.
        gdelt_locations: Ubicaciones de GDELT (pistas).
        gdelt_themes: Temas de GDELT.
    """

    source: str
    url: str
    title: str
    snippet: str | None
    source_name: str | None
    source_domain: str | None
    published_at: datetime
    language: str | None
    gdelt_states: tuple[str, ...] = ()
    gdelt_locations: tuple[GdeltLocation, ...] = ()
    gdelt_themes: tuple[str, ...] = ()

    @property
    def text_norm(self) -> str:
        """Título y fragmento normalizados: sobre esto busca ``indice_local``."""
        return normalize_name(f"{self.title} {self.snippet or ''}")

    @classmethod
    def create(  # noqa: PLR0913 — un argumento por campo de la nota, todos por nombre (*)
        cls,
        *,
        source: str,
        url: str,
        title: str | None,
        published_at: datetime | None,
        snippet: str | None = None,
        source_name: str | None = None,
        source_domain: str | None = None,
        language: str | None = None,
        gdelt_states: Sequence[str] = (),
        gdelt_locations: Sequence[GdeltLocation] = (),
        gdelt_themes: Sequence[str] = (),
    ) -> "NewsItem":
        """Valida y limpia una nota.

        Args:
            source: Origen.
            url: Link absoluto ``http(s)``.
            title: Título; no puede quedar vacío.
            published_at: Fecha con zona; sin fecha no se puede buscar por rango.
            snippet: Fragmento.
            source_name: Medio.
            source_domain: Dominio; si falta, se toma de la URL.
            language: Idioma.
            gdelt_states: Claves INEGI de estado.
            gdelt_locations: Ubicaciones de GDELT.
            gdelt_themes: Temas de GDELT.

        Returns:
            La nota.

        Raises:
            InvalidNewsError: Si falta URL web, título o fecha con zona.
        """
        clean_url = url.strip()
        parts = urlsplit(clean_url)
        if parts.scheme not in _WEB_SCHEMES or not parts.netloc:
            raise InvalidNewsError(f"URL no válida: {url!r}")
        clean_title = " ".join((title or "").split())
        if not clean_title:
            raise InvalidNewsError(f"Nota sin título: {url!r}")
        if published_at is None or published_at.tzinfo is None:
            raise InvalidNewsError(f"Nota sin fecha con zona: {url!r}")
        clean_snippet = " ".join((snippet or "").split()) or None
        return cls(
            source=source,
            url=clean_url,
            title=clean_title,
            snippet=clean_snippet,
            source_name=" ".join((source_name or "").split()) or None,
            source_domain=(source_domain or domain_of(clean_url) or "").lower() or None,
            published_at=published_at.astimezone(UTC),
            language=language,
            gdelt_states=tuple(dict.fromkeys(gdelt_states)),
            gdelt_locations=tuple(gdelt_locations),
            gdelt_themes=tuple(dict.fromkeys(gdelt_themes)),
        )


def keep_gdelt_note(language: str | None, locations: Sequence[GdeltLocation]) -> bool:
    """Dice si una nota del GKG entra al índice: en español y con México.

    Args:
        language: Idioma original según GDELT (``spa``).
        locations: Ubicaciones que encontró GDELT.

    Returns:
        ``True`` si está en español y alguna ubicación es de México.
    """
    return language == SPANISH and any(loc.country == MEXICO_FIPS for loc in locations)


def inegi_states(
    locations: Sequence[GdeltLocation], fips_to_inegi: dict[str, str]
) -> tuple[str, ...]:
    """Claves INEGI de los estados de México donde GDELT ubicó una nota.

    Args:
        locations: Ubicaciones de GDELT.
        fips_to_inegi: Tabla ``geodata/fips_inegi.csv`` (``MX07`` → ``05``).

    Returns:
        Claves INEGI sin repetir, en el orden en que aparecen. Las
        ubicaciones a nivel país (sin estado) no aportan clave.
    """
    states = [
        fips_to_inegi[loc.adm1]
        for loc in locations
        if loc.country == MEXICO_FIPS and loc.adm1 in fips_to_inegi
    ]
    return tuple(dict.fromkeys(states))
