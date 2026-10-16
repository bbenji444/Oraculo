"""Paginación por cursor (CLAUDE.md §6.3: nunca ``OFFSET``).

Un cursor es una marca opaca que dice "dame lo que sigue después de este
registro". Para las regiones el orden es alfabético por ``name_norm`` y, en
empate, por ``id``; el cursor guarda ese par en base64 para que el cliente
no dependa de su forma.

No hace: no consulta la base; solo codifica y decodifica cursores.
"""

import base64
import binascii
import json
from dataclasses import dataclass

from app.domain.errors import InvalidRequestError


@dataclass(frozen=True, slots=True)
class NameCursor:
    """Posición en una lista ordenada por (nombre normalizado, id).

    Attributes:
        name_norm: Nombre normalizado del último registro entregado.
        id: Id del último registro entregado.
    """

    name_norm: str
    id: int


def encode_cursor(cursor: NameCursor) -> str:
    """Convierte la posición en un texto opaco para la URL.

    Args:
        cursor: Posición del último registro entregado.

    Returns:
        Texto base64 seguro para URL, sin relleno.
    """
    raw = json.dumps([cursor.name_norm, cursor.id], ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> NameCursor:
    """Recupera la posición desde el texto del cursor.

    Args:
        token: Cursor recibido del cliente.

    Returns:
        La posición.

    Raises:
        InvalidRequestError: Si el cursor está dañado o no es de esta API.
    """
    try:
        padded = token + "=" * (-len(token) % 4)
        name_norm, region_id = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if not isinstance(name_norm, str) or not isinstance(region_id, int):
            raise ValueError("forma inesperada")
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise InvalidRequestError(
            "El cursor de paginación no es válido; vuelve a pedir la primera página."
        ) from exc
    return NameCursor(name_norm, region_id)


@dataclass(frozen=True, slots=True)
class Page[T]:
    """Una página de resultados.

    Attributes:
        items: Registros de esta página.
        next_cursor: Cursor para pedir la siguiente, o ``None`` si es la última.
    """

    items: tuple[T, ...]
    next_cursor: str | None
