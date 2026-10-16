"""Descarga de archivos de geodatos.

Incluye la extracción remota de un solo archivo de dentro de un ZIP grande.

Por qué existe: el ZIP nacional de INEGI pesa 2.9 GB, pero solo se necesita
el marco integrado que trae dentro (256 MB). Un ZIP guarda al final un
índice con la posición de cada archivo; como el servidor acepta peticiones
HTTP Range ("dame los bytes del X al Y"), se lee el índice, se ubica el
archivo y se bajan solo sus bytes (ADR-0008).

La red está detrás de funciones inyectables (``RangeFetcher``,
``WholeFetcher``) para poder probar todo sin internet.

No hace: no extrae ni interpreta los shapefiles (eso es ``inspeccion``).
"""

import hashlib
import io
import json
import logging
import struct
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from collections.abc import Buffer, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

logger = logging.getLogger(__name__)

# (url, primer_byte, ultimo_byte) -> bytes. Rango inclusivo, como en HTTP.
RangeFetcher = Callable[[str, int, int], bytes]
# url -> tamaño en bytes (Content-Length).
SizeFetcher = Callable[[str], int]
# url -> contenido completo.
WholeFetcher = Callable[[str], bytes]

# Tiempo máximo de espera por petición (CLAUDE.md §6.1: timeouts explícitos).
HTTP_TIMEOUT_SECONDS = 60
# Reintentos con espera exponencial: 2, 4, 8, 16 s ante fallas de red o 5xx/429.
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2
# Tamaño de cada petición Range. 8 MB: pocas peticiones y poca memoria.
CHUNK_BYTES = 8 * 1024 * 1024
# Lectura del índice del ZIP: bloques chicos para bajar solo lo necesario.
INDEX_READ_BUFFER_BYTES = 64 * 1024
# Cabecera local de cada archivo dentro de un ZIP (formato PKZIP): 30 bytes
# fijos, seguidos del nombre y el campo "extra" de longitud variable.
_LOCAL_HEADER_SIZE = 30
_LOCAL_HEADER_SIGNATURE = b"PK\x03\x04"
_LOCAL_HEADER_NAME_LENGTHS = slice(26, 30)
# Lectura de archivos locales para calcular SHA-256 sin cargarlos en memoria.
_HASH_BLOCK_BYTES = 1024 * 1024
# Avance reportado cada 10 % de la descarga.
_PROGRESS_STEP_PERCENT = 10
_PERCENT = 100
# Respuestas que vale la pena reintentar: el servidor está ocupado o falló.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class GeodataDownloadError(Exception):
    """La descarga no se pudo completar (red, servidor o archivo inesperado)."""


class GeodataIntegrityError(GeodataDownloadError):
    """Lo descargado no coincide con lo que dice el ZIP (tamaño o CRC)."""


# --- Red (implementaciones reales con urllib) ---------------------------------


def _with_retries[T](description: str, action: Callable[[], T]) -> T:
    """Ejecuta ``action`` reintentando con espera exponencial ante fallas pasajeras."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return action()
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                raise GeodataDownloadError(f"{description}: HTTP {exc.code}") from exc
            reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise GeodataDownloadError(f"{description}: {exc}") from exc
            reason = type(exc).__name__
        wait = BACKOFF_BASE_SECONDS**attempt
        logger.warning(
            "Falla pasajera; se reintenta",
            extra={"description": description, "reason": reason, "wait_seconds": wait},
        )
        time.sleep(wait)
    raise AssertionError("inalcanzable")  # pragma: no cover


def http_fetch_range(url: str, start: int, end: int) -> bytes:
    """Descarga los bytes ``start..end`` (inclusivos) de ``url`` con HTTP Range.

    Args:
        url: Dirección del archivo.
        start: Primer byte.
        end: Último byte (inclusivo).

    Returns:
        Exactamente ``end - start + 1`` bytes.

    Raises:
        GeodataDownloadError: Si el servidor no respeta el rango o falla
            después de los reintentos.
    """
    expected = end - start + 1

    def fetch() -> bytes:
        request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})  # noqa: S310 — URL fija de geodata/fuentes.py, siempre https
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 — misma URL fija
            if response.status != HTTPStatus.PARTIAL_CONTENT:
                raise GeodataDownloadError(
                    f"El servidor no aceptó la petición por partes (HTTP {response.status})."
                )
            data: bytes = response.read()
        if len(data) != expected:
            # Conexión cortada a la mitad: se trata como falla pasajera.
            raise ConnectionError(f"se recibieron {len(data)} de {expected} bytes")
        return data

    return _with_retries(f"Rango {start}-{end} de {url}", fetch)


def http_content_length(url: str) -> int:
    """Pide solo las cabeceras (HEAD) y devuelve el tamaño del archivo.

    Args:
        url: Dirección del archivo.

    Returns:
        Tamaño en bytes según ``Content-Length``.

    Raises:
        GeodataDownloadError: Si el servidor no informa el tamaño.
    """

    def fetch() -> int:
        request = urllib.request.Request(url, method="HEAD")  # noqa: S310 — URL fija de geodata/fuentes.py
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 — misma URL fija
            length = response.headers.get("Content-Length")
        if length is None:
            raise GeodataDownloadError(f"{url} no informa su tamaño (Content-Length).")
        return int(length)

    return _with_retries(f"Tamaño de {url}", fetch)


def http_fetch_whole(url: str) -> bytes:
    """Descarga un archivo completo (para archivos chicos, como Natural Earth).

    Args:
        url: Dirección del archivo.

    Returns:
        El contenido completo.

    Raises:
        GeodataDownloadError: Si falla después de los reintentos.
    """

    def fetch() -> bytes:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 — URL fija de geodata/fuentes.py
            data: bytes = response.read()
        return data

    return _with_retries(f"Descarga de {url}", fetch)


@dataclass(frozen=True, slots=True)
class Fetchers:
    """Funciones de red que usa la descarga; las pruebas las reemplazan.

    Attributes:
        range: Pide un rango de bytes (HTTP Range).
        size: Pide el tamaño de un archivo (HEAD).
        whole: Descarga un archivo completo.
    """

    range: RangeFetcher = http_fetch_range
    size: SizeFetcher = http_content_length
    whole: WholeFetcher = http_fetch_whole


# --- Lectura remota del índice del ZIP ----------------------------------------


class _RemoteFile(io.RawIOBase):
    """Archivo de solo lectura cuyos bytes se piden por rangos al leer."""

    def __init__(self, url: str, size: int, fetch_range: RangeFetcher) -> None:
        self._url = url
        self._size = size
        self._fetch_range = fetch_range
        self._position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._position = offset
        elif whence == io.SEEK_CUR:
            self._position += offset
        else:
            self._position = self._size + offset
        return self._position

    def readinto(self, buffer: Buffer) -> int:
        view = memoryview(buffer).cast("B")
        if self._position >= self._size:
            return 0
        end = min(self._position + len(view), self._size) - 1
        data = self._fetch_range(self._url, self._position, end)
        view[: len(data)] = data
        self._position += len(data)
        return len(data)


@dataclass(frozen=True, slots=True)
class MemberLocation:
    """Dónde están, dentro del ZIP remoto, los bytes de un archivo.

    Attributes:
        name: Nombre del archivo dentro del ZIP.
        data_offset: Byte donde empiezan sus datos (después de su cabecera).
        compressed_size: Bytes que ocupa comprimido.
        file_size: Bytes que ocupa ya descomprimido.
        crc32: Suma de verificación CRC-32 del contenido descomprimido.
        compress_type: Método de compresión (0 sin compresión, 8 deflate).
    """

    name: str
    data_offset: int
    compressed_size: int
    file_size: int
    crc32: int
    compress_type: int


def locate_member(
    url: str, member: str, fetch_range: RangeFetcher, fetch_size: SizeFetcher
) -> MemberLocation:
    """Ubica un archivo dentro de un ZIP remoto leyendo solo su índice.

    Args:
        url: Dirección del ZIP remoto.
        member: Nombre del archivo buscado dentro del ZIP.
        fetch_range: Función para pedir rangos de bytes.
        fetch_size: Función para conocer el tamaño total del ZIP.

    Returns:
        La ubicación de sus datos.

    Raises:
        GeodataDownloadError: Si el archivo no está en el ZIP (el mensaje
            lista los que sí están) o la cabecera no es válida.
    """
    remote = _RemoteFile(url, fetch_size(url), fetch_range)
    with zipfile.ZipFile(io.BufferedReader(remote, buffer_size=INDEX_READ_BUFFER_BYTES)) as zf:
        try:
            info = zf.getinfo(member)
        except KeyError as exc:
            available = ", ".join(zf.namelist())
            raise GeodataDownloadError(
                f"El ZIP remoto no contiene '{member}'. Contiene: {available}"
            ) from exc

    header = fetch_range(url, info.header_offset, info.header_offset + _LOCAL_HEADER_SIZE - 1)
    if header[:4] != _LOCAL_HEADER_SIGNATURE:
        raise GeodataDownloadError(f"Cabecera inválida para '{member}' en el ZIP remoto.")
    name_length, extra_length = struct.unpack("<HH", header[_LOCAL_HEADER_NAME_LENGTHS])
    return MemberLocation(
        name=member,
        data_offset=info.header_offset + _LOCAL_HEADER_SIZE + name_length + extra_length,
        compressed_size=info.compress_size,
        file_size=info.file_size,
        crc32=info.CRC,
        compress_type=info.compress_type,
    )


def download_member(
    url: str,
    location: MemberLocation,
    destination: Path,
    fetch_range: RangeFetcher,
    chunk_bytes: int = CHUNK_BYTES,
) -> int:
    """Descarga y descomprime un archivo de dentro de un ZIP remoto.

    Baja solo sus bytes comprimidos, por bloques, y los descomprime al vuelo.
    Escribe primero en ``<destino>.part`` y solo renombra al final si el
    tamaño y el CRC coinciden con los del índice del ZIP: un archivo a medias
    nunca queda con el nombre final.

    Args:
        url: Dirección del ZIP remoto.
        location: Resultado de ``locate_member``.
        destination: Ruta final del archivo descomprimido.
        fetch_range: Función para pedir rangos de bytes.
        chunk_bytes: Tamaño de cada petición.

    Returns:
        Bytes escritos (tamaño descomprimido).

    Raises:
        GeodataDownloadError: Si el método de compresión no es soportado.
        GeodataIntegrityError: Si el tamaño o el CRC no coinciden.
    """
    if location.compress_type == zipfile.ZIP_DEFLATED:
        # wbits negativo: datos deflate "crudos", sin cabecera zlib, como en ZIP.
        decompressor = zlib.decompressobj(-zlib.MAX_WBITS)

        def inflate(data: bytes) -> bytes:
            return decompressor.decompress(data)

        def finish() -> bytes:
            return decompressor.flush()
    elif location.compress_type == zipfile.ZIP_STORED:

        def inflate(data: bytes) -> bytes:
            return data

        def finish() -> bytes:
            return b""
    else:
        raise GeodataDownloadError(
            f"Método de compresión no soportado ({location.compress_type}) en '{location.name}'."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    crc = 0
    written = 0
    next_report = _PROGRESS_STEP_PERCENT
    end_offset = location.data_offset + location.compressed_size
    try:
        with partial.open("wb") as out:
            for start in range(location.data_offset, end_offset, chunk_bytes):
                end = min(start + chunk_bytes, end_offset) - 1
                block = inflate(fetch_range(url, start, end))
                out.write(block)
                crc = zlib.crc32(block, crc)
                written += len(block)
                percent = (end - location.data_offset + 1) * _PERCENT // location.compressed_size
                if percent >= next_report:
                    logger.info(f"Descargado {percent} %")
                    next_report = (percent // _PROGRESS_STEP_PERCENT + 1) * _PROGRESS_STEP_PERCENT
            tail = finish()
            out.write(tail)
            crc = zlib.crc32(tail, crc)
            written += len(tail)
        if written != location.file_size or crc != location.crc32:
            raise GeodataIntegrityError(
                f"'{location.name}' llegó dañado: {written} bytes y CRC {crc:08x}; "
                f"se esperaban {location.file_size} bytes y CRC {location.crc32:08x}."
            )
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return written


# --- Manifiesto ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """Registro de una descarga (especificación §12: URL, fecha y edición).

    Attributes:
        key: Identificador de la fuente.
        title: Nombre legible.
        url: Dirección de origen.
        member: Archivo extraído de dentro del ZIP remoto, si aplica.
        edition: Edición de la fuente.
        license: Términos de uso.
        path: Ruta relativa a ``geodata/raw``.
        size: Tamaño en bytes.
        sha256: Huella SHA-256 del archivo guardado.
        downloaded_at: Fecha y hora UTC de la descarga (ISO 8601).
    """

    key: str
    title: str
    url: str
    member: str | None
    edition: str
    license: str
    path: str
    size: int
    sha256: str
    downloaded_at: str


def sha256_file(path: Path) -> str:
    """Calcula la huella SHA-256 de un archivo leyéndolo por bloques.

    Args:
        path: Archivo a leer.

    Returns:
        La huella en hexadecimal.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_HASH_BLOCK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, ManifestEntry]:
    """Lee el manifiesto; si no existe, devuelve uno vacío.

    Args:
        path: Ruta de ``MANIFIESTO.json``.

    Returns:
        Las entradas indexadas por ``key``.
    """
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {item["key"]: ManifestEntry(**item) for item in raw["descargas"]}


def save_manifest(path: Path, entries: dict[str, ManifestEntry]) -> None:
    """Guarda el manifiesto en JSON legible (UTF-8, ordenado por ``key``).

    Args:
        path: Ruta de ``MANIFIESTO.json``.
        entries: Entradas a guardar.
    """
    payload = {"descargas": [asdict(entries[key]) for key in sorted(entries)]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_up_to_date(entry: ManifestEntry | None, raw_dir: Path) -> bool:
    """Indica si una descarga ya existe y no cambió desde que se registró.

    Args:
        entry: Entrada del manifiesto, o ``None`` si nunca se descargó.
        raw_dir: Carpeta ``geodata/raw``.

    Returns:
        ``True`` si el archivo existe y su SHA-256 coincide con el registrado.
    """
    if entry is None:
        return False
    file_path = raw_dir / entry.path
    return file_path.exists() and sha256_file(file_path) == entry.sha256


def utc_now_iso() -> str:
    """Fecha y hora actual en UTC, en formato ISO 8601 (CLAUDE.md §6.3)."""
    return datetime.now(tz=UTC).isoformat(timespec="seconds")
