"""Lectura de los archivos GKG "translingual" de GDELT (ADR-0013).

GDELT publica cada 15 minutos ``lastupdate-translation.txt`` con tres líneas
``<bytes> <md5> <url>``; la del GKG termina en ``.translation.gkg.csv.zip``.
El ZIP trae un CSV separado por tabuladores, sin encabezado, de 27 columnas
(GKG 2.1). Se usan:

====  ======================  =============================================
 #    Columna                 Uso
====  ======================  =============================================
 1    DATE                    Fecha de la nota (``YYYYMMDDHHMMSS``, UTC)
 3    SourceCommonName        Dominio del medio
 4    DocumentIdentifier      URL de la nota
 8    V2Themes                Temas (``TEMA,posición;…``)
 10   V2Locations             Ubicaciones (``tipo#nombre#país#ADM1#ADM2#lat#lon#id#pos;…``)
 25   TranslationInfo         Idioma original (``srclc:spa;…``)
 26   Extras                  ``<PAGE_TITLE>`` con el título (entidades HTML)
====  ======================  =============================================

Confirmado con el archivo real ``20261016191500.translation.gkg.csv.zip``
(2,197 filas, 27 columnas). Documentación: GKG 2.1 Codebook,
http://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf

Términos (https://www.gdeltproject.org/about.html): uso sin restricción ni
costo, citando al GDELT Project con un link.

No hace: no guarda nada (eso es el caso de uso de ingesta).
"""

import csv
import hashlib
import html
import io
import re
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.adapters.providers.http import ProviderHttpClient
from app.domain.news_index import (
    GDELT_SOURCE,
    GdeltLocation,
    InvalidNewsError,
    NewsItem,
    inegi_states,
    keep_gdelt_note,
)

LASTUPDATE_URL = "https://data.gdeltproject.org/gdeltv2/lastupdate-translation.txt"
GKG_SUFFIX = ".translation.gkg.csv.zip"
GKG_COLUMNS = 27
COL_DATE, COL_SOURCE, COL_URL, COL_THEMES, COL_LOCATIONS = 1, 3, 4, 8, 10
COL_TRANSLATION, COL_EXTRAS = 25, 26
_GKG_DATE = "%Y%m%d%H%M%S"
_TITLE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.DOTALL)
_LANGUAGE = re.compile(r"srclc:(\w+)")
# Temas que se conservan por nota: suficientes como pista sin inflar la base.
MAX_THEMES = 30
_LOCATION_PARTS = 7
# Cada línea del anuncio: "<bytes> <md5> <url>".
_LASTUPDATE_FIELDS = 3


class GkgFileError(RuntimeError):
    """El archivo de GDELT no llegó completo o no tiene el formato esperado."""


@dataclass(frozen=True, slots=True)
class GkgFile:
    """Un archivo GKG anunciado por GDELT.

    Attributes:
        url: Dirección del ZIP.
        size: Tamaño en bytes que anuncia GDELT.
        md5: Huella MD5 que anuncia GDELT.
    """

    url: str
    size: int
    md5: str

    @property
    def name(self) -> str:
        """Nombre del archivo ("20261016191500.translation.gkg.csv.zip")."""
        return self.url.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class GkgParseResult:
    """Notas que salieron de un archivo GKG.

    Attributes:
        items: Notas en español con México, listas para el índice.
        seen: Filas leídas.
        discarded: Filas en español con México que no se pudieron usar
            (sin título o sin URL web).
    """

    items: tuple[NewsItem, ...]
    seen: int
    discarded: int


def parse_lastupdate(text: str) -> GkgFile:
    """Encuentra el GKG en ``lastupdate-translation.txt``.

    Args:
        text: Contenido del archivo (tres líneas ``bytes md5 url``).

    Returns:
        El archivo GKG anunciado.

    Raises:
        GkgFileError: Si no hay una línea de GKG válida.
    """
    for line in text.splitlines():
        parts = line.split()
        if (
            len(parts) == _LASTUPDATE_FIELDS
            and parts[2].endswith(GKG_SUFFIX)
            and parts[0].isdigit()
        ):
            # GDELT anuncia http://; el servidor redirige a https.
            return GkgFile(parts[2].replace("http://", "https://", 1), int(parts[0]), parts[1])
    raise GkgFileError("lastupdate-translation.txt no anuncia ningún GKG.")


def verify(data: bytes, file: GkgFile) -> None:
    """Comprueba que el ZIP llegó completo con el tamaño y el MD5 que anuncia GDELT.

    Args:
        data: Bytes descargados.
        file: Archivo anunciado.

    Raises:
        GkgFileError: Si no coinciden.
    """
    if len(data) != file.size:
        raise GkgFileError(f"{file.name}: llegaron {len(data)} bytes, se esperaban {file.size}.")
    digest = hashlib.md5(data, usedforsecurity=False).hexdigest()
    if digest != file.md5:
        raise GkgFileError(f"{file.name}: el MD5 no coincide ({digest} ≠ {file.md5}).")


def parse_locations(field: str) -> tuple[GdeltLocation, ...]:
    """Lee el campo V2Locations.

    Args:
        field: ``tipo#nombre#país#ADM1#ADM2#lat#lon#id#pos`` separados por ``;``.

    Returns:
        Las ubicaciones legibles; las mal formadas se ignoran.
    """
    locations = []
    for raw in field.split(";"):
        parts = raw.split("#")
        if len(parts) < _LOCATION_PARTS or not parts[0].isdigit():
            continue
        try:
            lat = float(parts[5]) if parts[5] else None
            lon = float(parts[6]) if parts[6] else None
        except ValueError:
            lat = lon = None
        locations.append(GdeltLocation(int(parts[0]), parts[1], parts[2], parts[3], lat, lon))
    return tuple(locations)


def _themes(field: str) -> tuple[str, ...]:
    names = [item.split(",")[0] for item in field.split(";") if item]
    return tuple(dict.fromkeys(names))[:MAX_THEMES]


def _title(extras: str) -> str | None:
    found = _TITLE.search(extras)
    return html.unescape(found.group(1)).strip() if found else None


def _language(translation: str) -> str | None:
    found = _LANGUAGE.search(translation)
    return found.group(1) if found else None


def _date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, _GKG_DATE).replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_rows(rows: Sequence[Sequence[str]], fips_to_inegi: dict[str, str]) -> GkgParseResult:
    """Convierte filas del GKG en notas del índice (solo español con México).

    Args:
        rows: Filas del CSV (27 columnas).
        fips_to_inegi: Tabla FIPS → INEGI (``geodata/fips_inegi.csv``).

    Returns:
        Las notas que entran al índice y los conteos.
    """
    items: list[NewsItem] = []
    discarded = 0
    for row in rows:
        if len(row) < GKG_COLUMNS:
            continue
        locations = parse_locations(row[COL_LOCATIONS])
        if not keep_gdelt_note(_language(row[COL_TRANSLATION]), locations):
            continue
        try:
            items.append(
                NewsItem.create(
                    source=GDELT_SOURCE,
                    url=row[COL_URL],
                    title=_title(row[COL_EXTRAS]),
                    published_at=_date(row[COL_DATE]),
                    source_domain=row[COL_SOURCE] or None,
                    language="es",
                    gdelt_states=inegi_states(locations, fips_to_inegi),
                    gdelt_locations=[loc for loc in locations if loc.country == "MX"],
                    gdelt_themes=_themes(row[COL_THEMES]),
                )
            )
        except InvalidNewsError:
            discarded += 1
    return GkgParseResult(tuple(items), len(rows), discarded)


def read_zip(data: bytes) -> list[list[str]]:
    """Abre el ZIP del GKG y devuelve sus filas.

    Args:
        data: Bytes del ZIP ya verificado.

    Returns:
        Filas separadas por tabulador.

    Raises:
        GkgFileError: Si el ZIP está dañado o vacío.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if not names:
                raise GkgFileError("El ZIP del GKG viene vacío.")
            # zipfile verifica el CRC de cada archivo al leerlo.
            content = archive.read(names[0])
    except zipfile.BadZipFile as exc:
        raise GkgFileError("El ZIP del GKG está dañado.") from exc
    # GDELT publica en UTF-8; un byte dañado no debe tumbar el archivo entero.
    text = content.decode("utf-8", errors="replace")
    csv.field_size_limit(len(text) + 1)
    return list(csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))


class GdeltGkgSource:
    """Baja y lee el GKG translingual más reciente de GDELT."""

    def __init__(self, http: ProviderHttpClient, fips_to_inegi: dict[str, str]) -> None:
        """Recibe el cliente HTTP y la tabla FIPS → INEGI.

        Args:
            http: Cliente HTTP (tiempos, reintentos, 429).
            fips_to_inegi: Equivalencias de estados.
        """
        self._http = http
        self._fips = fips_to_inegi

    async def latest(self) -> GkgFile:
        """Archivo GKG que GDELT anuncia como el más reciente.

        Returns:
            El archivo anunciado.

        Raises:
            GkgFileError: Si el anuncio no trae un GKG.
            ProviderError: Si GDELT no responde.
        """
        response = await self._http.get(LASTUPDATE_URL, {})
        return parse_lastupdate(response.text)

    async def fetch(self, file: GkgFile) -> tuple[GkgParseResult, int]:
        """Baja, verifica y lee un archivo GKG.

        Args:
            file: Archivo anunciado.

        Returns:
            Las notas leídas y los bytes descargados.

        Raises:
            GkgFileError: Si llegó incompleto, dañado o con otro formato.
            ProviderError: Si GDELT no responde.
        """
        response = await self._http.get(file.url, {})
        data = response.content
        verify(data, file)
        return parse_rows(read_zip(data), self._fips), len(data)
