"""Lectura mínima de archivos DBF (la tabla de atributos de un shapefile).

Por qué existe: antes de cargar, hay que ver los **bytes crudos** de los
nombres para detectar su encoding (CLAUDE.md §6.4). Si se leen con una
librería que ya decodifica, un encoding equivocado convierte "Peñón" en
"PeÃ±Ã³n" sin avisar. Este lector no decodifica nada: entrega bytes.

Formato (dBase III, el que usan los shapefiles): una cabecera de 32 bytes,
un descriptor de 32 bytes por campo, un byte 0x0D y luego los registros de
largo fijo, cada uno con un byte inicial de "borrado".

No hace: no interpreta números ni fechas; solo extrae campos de texto.
"""

import struct
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

# Estructura de la cabecera dBase III (bytes 4-11): número de registros
# (uint32), largo de la cabecera (uint16) y largo de cada registro (uint16).
_HEADER_SIZE = 32
_HEADER_COUNTS = struct.Struct("<IHH")
_HEADER_COUNTS_OFFSET = 4
_FIELD_DESCRIPTOR_SIZE = 32
_FIELD_NAME_SIZE = 11
_FIELD_LENGTH_OFFSET = 16
_HEADER_TERMINATOR = 0x0D
# Primer byte de cada registro: "*" si el registro está marcado como borrado.
_DELETED_FLAG = ord("*")


class DbfError(Exception):
    """El archivo no tiene el formato DBF esperado o falta un campo."""


@dataclass(frozen=True, slots=True)
class DbfField:
    """Descripción de un campo del DBF.

    Attributes:
        name: Nombre del campo (por ejemplo, ``NOMGEO``).
        offset: Posición del campo dentro del registro (sin el byte de borrado).
        length: Largo en bytes.
    """

    name: str
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class DbfHeader:
    """Cabecera del DBF.

    Attributes:
        record_count: Número de registros.
        header_length: Bytes antes del primer registro.
        record_length: Bytes de cada registro (incluye el byte de borrado).
        fields: Campos en orden.
    """

    record_count: int
    header_length: int
    record_length: int
    fields: tuple[DbfField, ...]

    def field(self, name: str) -> DbfField:
        """Busca un campo por nombre.

        Args:
            name: Nombre del campo, sin importar mayúsculas.

        Returns:
            El campo.

        Raises:
            DbfError: Si no existe; el mensaje lista los campos disponibles.
        """
        for candidate in self.fields:
            if candidate.name.upper() == name.upper():
                return candidate
        available = ", ".join(f.name for f in self.fields)
        raise DbfError(f"El DBF no tiene el campo '{name}'. Campos: {available}")


def read_header(path: Path) -> DbfHeader:
    """Lee la cabecera y la lista de campos de un DBF.

    Args:
        path: Ruta del archivo ``.dbf``.

    Returns:
        La cabecera.

    Raises:
        DbfError: Si el archivo es más corto que una cabecera o está mal formado.
    """
    with path.open("rb") as handle:
        header = handle.read(_HEADER_SIZE)
        if len(header) < _HEADER_SIZE:
            raise DbfError(f"{path.name} es demasiado corto para ser un DBF.")
        record_count, header_length, record_length = _HEADER_COUNTS.unpack_from(
            header, _HEADER_COUNTS_OFFSET
        )
        fields: list[DbfField] = []
        offset = 0
        while True:
            descriptor = handle.read(_FIELD_DESCRIPTOR_SIZE)
            if not descriptor or descriptor[0] == _HEADER_TERMINATOR:
                break
            if len(descriptor) < _FIELD_DESCRIPTOR_SIZE:
                raise DbfError(f"{path.name}: descriptor de campo incompleto.")
            name = descriptor[:_FIELD_NAME_SIZE].split(b"\x00", 1)[0].decode("ascii")
            length = descriptor[_FIELD_LENGTH_OFFSET]
            fields.append(DbfField(name=name, offset=offset, length=length))
            offset += length
    return DbfHeader(record_count, header_length, record_length, tuple(fields))


def iter_raw_values(path: Path, field_names: Sequence[str]) -> Iterator[tuple[bytes, ...]]:
    """Recorre los registros y entrega los bytes crudos de los campos pedidos.

    Los bytes se entregan sin decodificar y sin los espacios de relleno de la
    derecha. Los registros marcados como borrados se omiten.

    Args:
        path: Ruta del archivo ``.dbf``.
        field_names: Campos a extraer, en el orden deseado.

    Yields:
        Una tupla de bytes por registro, en el orden de ``field_names``.

    Raises:
        DbfError: Si algún campo no existe.
    """
    header = read_header(path)
    fields = [header.field(name) for name in field_names]
    with path.open("rb") as handle:
        handle.seek(header.header_length)
        for _ in range(header.record_count):
            record = handle.read(header.record_length)
            if len(record) < header.record_length:
                break
            if record[0] == _DELETED_FLAG:
                continue
            body = record[1:]
            yield tuple(body[f.offset : f.offset + f.length].rstrip(b" \x00") for f in fields)
