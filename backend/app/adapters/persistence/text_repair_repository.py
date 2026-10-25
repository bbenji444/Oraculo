"""Lectura por lotes y guardado de textos reparados en PostgreSQL (F12.1).

Implementa ``StoredTextPort`` para ``make reparar-texto``. Cada tabla tiene
su llave y sus columnas de texto. Al guardar se recalculan las columnas
normalizadas que dependen del título, con las mismas funciones que usa la
ingesta, para que la búsqueda siga encontrando la nota:

- ``news_index.text_norm`` ← ``index_text_norm(title, snippet)``.
- ``articles.title_norm`` ← ``normalize_name(title)``.

Paginación por cursor (``WHERE llave > :after ORDER BY llave``), nunca
``OFFSET`` (CLAUDE.md §6.3). Cada ``save`` es una transacción: un commit por
lote.

No hace: no decide qué está roto ni pide confirmación.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.ports.text_repair import StoredRow, TextTable
from app.domain.names import normalize_name
from app.domain.news_index import index_text_norm


@dataclass(frozen=True, slots=True)
class _Spec:
    key: str
    columns: tuple[str, ...]


# Columnas de texto que vienen de las fuentes. ``articles.summary`` la escribe
# la IA a partir del texto, pero se revisa igual: si el texto entró roto, el
# resumen pudo copiarlo.
_SPECS: dict[TextTable, _Spec] = {
    "news_index": _Spec("id", ("title", "snippet", "source_name")),
    "articles": _Spec("id", ("title", "snippet", "source_name", "summary")),
    "article_texts": _Spec("article_id", ("body",)),
}


def _norm_updates(table: TextTable, fields: dict[str, str | None]) -> dict[str, str]:
    """Columnas normalizadas que hay que recalcular con los textos nuevos."""
    title = fields.get("title")
    if title is None:
        return {}
    if table == "news_index":
        return {"text_norm": index_text_norm(title, fields.get("snippet"))}
    if table == "articles":
        return {"title_norm": normalize_name(title)}
    return {}


class PostgresStoredText:
    """``StoredTextPort`` sobre PostgreSQL.

    Args:
        engine: Motor asíncrono de SQLAlchemy.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def fetch(self, table: TextTable, after_id: int, limit: int) -> Sequence[StoredRow]:
        """Lote de renglones después de ``after_id``.

        Args:
            table: Tabla a leer.
            after_id: Última llave del lote anterior.
            limit: Tamaño del lote.

        Returns:
            Los renglones en orden de llave.
        """
        spec = _SPECS[table]
        sql = text(
            f"SELECT {spec.key} AS row_id, {', '.join(spec.columns)} FROM {table} "  # noqa: S608 — tabla y columnas salen de _SPECS, texto fijo del módulo
            f"WHERE {spec.key} > :after ORDER BY {spec.key} LIMIT :limit"
        )
        async with self._engine.connect() as conn:
            result = await conn.execute(sql, {"after": after_id, "limit": limit})
            return [
                StoredRow(
                    row_id=row.row_id,
                    fields={column: getattr(row, column) for column in spec.columns},
                )
                for row in result
            ]

    async def save(self, table: TextTable, rows: Sequence[StoredRow]) -> None:
        """Guarda los textos reparados y sus columnas normalizadas.

        Args:
            table: Tabla a escribir.
            rows: Renglones con sus textos nuevos.
        """
        spec = _SPECS[table]
        async with self._engine.begin() as conn:
            for row in rows:
                fields = dict(row.fields)
                values: dict[str, Any] = {**fields, **_norm_updates(table, fields)}
                assignments = [f"{column} = :{column}" for column in values]
                if table == "articles":
                    assignments.append("updated_at = now()")
                await conn.execute(
                    text(
                        f"UPDATE {table} SET {', '.join(assignments)} "  # noqa: S608 — tabla y columnas salen de _SPECS, texto fijo del módulo
                        f"WHERE {spec.key} = :row_id"
                    ),
                    {**values, "row_id": row.row_id},
                )
