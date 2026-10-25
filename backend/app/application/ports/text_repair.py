"""Puerto para leer y corregir los textos ya guardados (reparación de Mojibake, F12.1).

El caso de uso ``RepairStoredText`` recorre las tablas con textos de las
fuentes y le pide a este puerto los renglones por lotes y que guarde los
reparados. La implementación (``adapters/persistence``) sabe de SQL y de
qué columnas normalizadas hay que recalcular; el caso de uso no.

No hace: no decide qué está roto (eso es ``app.domain.text_repair``).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

# Tablas con texto de las fuentes. Medido el 24/10/2026: el Mojibake estaba
# en ``news_index.title`` (396), ``articles.title`` (5) y un cuerpo de
# ``article_texts``; las demás columnas de texto venían limpias.
TextTable = Literal["news_index", "articles", "article_texts"]
TEXT_TABLES: tuple[TextTable, ...] = ("news_index", "articles", "article_texts")


@dataclass(frozen=True, slots=True)
class StoredRow:
    """Un renglón con sus textos.

    Attributes:
        row_id: Llave del renglón (``id``, o ``article_id`` en ``article_texts``).
        fields: Columna → texto (``None`` si está vacía).
    """

    row_id: int
    fields: Mapping[str, str | None]


class StoredTextPort(Protocol):
    """Lectura por lotes y guardado de textos ya reparados."""

    async def fetch(self, table: TextTable, after_id: int, limit: int) -> Sequence[StoredRow]:
        """Renglones con llave mayor que ``after_id``, en orden, hasta ``limit``.

        Args:
            table: Tabla a leer.
            after_id: Última llave del lote anterior (0 al empezar).
            limit: Tamaño del lote.

        Returns:
            Los renglones; una lista vacía cuando ya no hay más.
        """
        ...

    async def save(self, table: TextTable, rows: Sequence[StoredRow]) -> None:
        """Guarda los textos reparados en una sola transacción.

        También recalcula las columnas normalizadas que dependen de ellos
        (``title_norm``, ``text_norm``).

        Args:
            table: Tabla a escribir.
            rows: Renglones con sus textos nuevos.
        """
        ...
