"""Repositorio del catálogo de regiones sobre PostgreSQL + PostGIS.

Implementa ``RegionRepositoryPort`` con SQL explícito (ADR-0008: sin
GeoAlchemy2), para que las consultas sean legibles y se puedan copiar a
DBeaver o ``psql`` tal cual.

Cómo usa los índices de la migración 0002:
- Listas por nivel o por padre: (``level``|``parent_id``, ``name_norm``, ``id``)
  con paginación por cursor ``(name_norm, id) > (:n, :id)``, nunca OFFSET.
- Búsqueda: trigramas sobre ``name_norm`` (``LIKE`` y ``%``) y GIN de alias.
- Punto: GIST de ``geom`` con ``ST_Contains``.

No hace: no aplica reglas de negocio (límites, validaciones): eso es de los
casos de uso.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.pagination import NameCursor
from app.domain.region import BoundingBox, GeoPoint, Region, RegionLevel, RegionRef

# Columnas que arman una Region. La geometría completa nunca se lee aquí.
_COLUMNS = """
    r.id, r.level::text AS level, r.code, r.name, r.name_norm, r.display_prefix,
    r.country_code, r.parent_id, ST_X(r.centroid) AS lon, ST_Y(r.centroid) AS lat,
    r.bbox, r.geom IS NOT NULL AS has_polygon, r.aliases, r.population
"""
# Profundidad del nivel (país 1 … localidad 4) para ordenar en SQL.
_LEVEL_DEPTH = (
    "array_position(ARRAY['country', 'state', 'municipality', 'locality']::region_level[], r.level)"
)
_AFTER = "AND (CAST(:after_name AS text) IS NULL OR (r.name_norm, r.id) > (:after_name, :after_id))"


def _escape_like(value: str) -> str:
    """Escapa los comodines de LIKE para que el texto se busque literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _to_region(row: RowMapping) -> Region:
    west, south, east, north = row["bbox"]
    return Region(
        id=row["id"],
        level=RegionLevel(row["level"]),
        code=row["code"],
        name=row["name"],
        name_norm=row["name_norm"],
        display_prefix=row["display_prefix"],
        country_code=row["country_code"],
        parent_id=row["parent_id"],
        point=GeoPoint(row["lon"], row["lat"]),
        bbox=BoundingBox(west, south, east, north),
        has_polygon=row["has_polygon"],
        aliases=tuple(row["aliases"]),
        population=row["population"],
    )


def _cursor_params(after: NameCursor | None) -> dict[str, Any]:
    return {
        "after_name": after.name_norm if after else None,
        "after_id": after.id if after else 0,
    }


class PostgresRegionRepository:
    """Consultas de solo lectura sobre la tabla ``regions``."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido de la aplicación.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def _fetch(self, sql: str, params: Mapping[str, Any]) -> list[Region]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(sql), dict(params))).mappings().all()
        return [_to_region(row) for row in rows]

    async def list_by_level(
        self, level: RegionLevel, after: NameCursor | None, limit: int
    ) -> list[Region]:
        """Ver ``RegionRepositoryPort.list_by_level``."""
        return await self._fetch(
            f"SELECT {_COLUMNS} FROM regions r WHERE r.level = CAST(:level AS region_level) "  # noqa: S608 — fragmentos SQL constantes del módulo
            f"{_AFTER} ORDER BY r.name_norm, r.id LIMIT :limit",
            {"level": level.value, "limit": limit, **_cursor_params(after)},
        )

    async def list_children(
        self, parent_id: int, after: NameCursor | None, limit: int
    ) -> list[Region]:
        """Ver ``RegionRepositoryPort.list_children``."""
        return await self._fetch(
            f"SELECT {_COLUMNS} FROM regions r WHERE r.parent_id = :parent_id "  # noqa: S608 — fragmentos SQL constantes del módulo
            f"{_AFTER} ORDER BY r.name_norm, r.id LIMIT :limit",
            {"parent_id": parent_id, "limit": limit, **_cursor_params(after)},
        )

    async def get(self, region_id: int) -> Region | None:
        """Ver ``RegionRepositoryPort.get``."""
        rows = await self._fetch(
            f"SELECT {_COLUMNS} FROM regions r WHERE r.id = :id",  # noqa: S608 — fragmentos SQL constantes del módulo
            {"id": region_id},
        )
        return rows[0] if rows else None

    async def ancestors(self, region_id: int) -> list[RegionRef]:
        """Ver ``RegionRepositoryPort.ancestors``."""
        sql = """
            WITH RECURSIVE chain AS (
                SELECT p.id, p.level, p.code, p.name, p.parent_id, 1 AS distance
                FROM regions r JOIN regions p ON p.id = r.parent_id
                WHERE r.id = :id
                UNION ALL
                SELECT p.id, p.level, p.code, p.name, p.parent_id, c.distance + 1
                FROM chain c JOIN regions p ON p.id = c.parent_id
            )
            SELECT id, level::text AS level, code, name FROM chain ORDER BY distance DESC
        """
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(sql), {"id": region_id})).mappings().all()
        return [RegionRef(r["id"], RegionLevel(r["level"]), r["code"], r["name"]) for r in rows]

    async def search(self, query_norm: str, limit: int) -> list[Region]:
        """Ver ``RegionRepositoryPort.search``.

        Orden de relevancia: nombre o alias exacto → el nombre empieza con
        el texto → alguna palabra empieza con el texto → parecido por
        trigramas. En empate, primero lo más general (estado antes que
        localidad) y luego lo más parecido.
        """
        escaped = _escape_like(query_norm)
        sql = f"""
            SELECT {_COLUMNS},
                   CASE
                       WHEN r.name_norm = :q OR r.aliases_norm @> ARRAY[:q] THEN 0
                       WHEN r.name_norm LIKE :prefix THEN 1
                       WHEN r.name_norm LIKE :word_prefix THEN 2
                       ELSE 3
                   END AS relevance
            FROM regions r
            WHERE r.name_norm LIKE :contains
               OR r.aliases_norm @> ARRAY[:q]
               OR r.name_norm % :q
            ORDER BY relevance, {_LEVEL_DEPTH}, similarity(r.name_norm, :q) DESC,
                     r.name_norm, r.id
            LIMIT :limit
        """  # noqa: S608 — fragmentos SQL constantes del módulo; el texto del usuario va como parámetro
        return await self._fetch(
            sql,
            {
                "q": query_norm,
                "prefix": f"{escaped}%",
                "word_prefix": f"% {escaped}%",
                "contains": f"%{escaped}%",
                "limit": limit,
            },
        )

    async def find_at_point(self, point: GeoPoint, level: RegionLevel | None) -> Region | None:
        """Ver ``RegionRepositoryPort.find_at_point``."""
        rows = await self._fetch(
            f"""
            SELECT {_COLUMNS} FROM regions r
            WHERE r.geom IS NOT NULL
              AND ST_Contains(r.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
              AND (CAST(:level AS region_level) IS NULL OR r.level = CAST(:level AS region_level))
            ORDER BY {_LEVEL_DEPTH} DESC
            LIMIT 1
            """,  # noqa: S608 — fragmentos SQL constantes del módulo
            {"lon": point.lon, "lat": point.lat, "level": level.value if level else None},
        )
        return rows[0] if rows else None
