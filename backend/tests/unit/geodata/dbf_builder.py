"""Construye archivos DBF pequeños para las pruebas (formato dBase III)."""

import struct
from collections.abc import Sequence
from pathlib import Path

DBF_VERSION = 0x03
HEADER_TERMINATOR = b"\r"
FILE_TERMINATOR = b"\x1a"


def write_dbf(
    path: Path,
    fields: Sequence[tuple[str, int]],
    records: Sequence[Sequence[bytes]],
    deleted: Sequence[int] = (),
) -> None:
    """Escribe un DBF con campos de texto.

    Args:
        path: Dónde escribirlo.
        fields: (nombre, largo) de cada campo de texto.
        records: Valores en bytes crudos (ya codificados) por registro.
        deleted: Índices de registros marcados como borrados.
    """
    header_length = 32 + 32 * len(fields) + 1
    record_length = 1 + sum(length for _, length in fields)
    header = struct.pack(
        "<BBBBIHH20x", DBF_VERSION, 126, 10, 15, len(records), header_length, record_length
    )
    descriptors = b"".join(
        struct.pack("<11sc4xBB14x", name.encode("ascii"), b"C", length, 0)
        for name, length in fields
    )
    body = b""
    for index, values in enumerate(records):
        flag = b"*" if index in deleted else b" "
        body += flag + b"".join(
            value.ljust(length, b" ") for value, (_, length) in zip(values, fields, strict=True)
        )
    path.write_bytes(header + descriptors + HEADER_TERMINATOR + body + FILE_TERMINATOR)
