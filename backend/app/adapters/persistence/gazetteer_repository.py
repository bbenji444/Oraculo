"""``GazetteerPort`` sobre ``regions``: búsquedas por nombre para el geolocalizador (§11).

Compara siempre con ``name_norm`` y ``aliases_norm`` (la normalización del
catálogo, que conserva la Ñ). Los parecidos usan ``similarity`` de
``pg_trgm`` con el índice de trigramas de ``name_norm``.

No hace: no decide cuál región gana (eso es ``app.domain.geocoding``).
"""

from collections.abc import Mapping, Sequence

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.geocoding import MEXICO_ISO3, Neighborhood, Place
from app.domain.region import RegionLevel

_COLUMNS = """
    r.id, r.code, r.level::text AS level, r.name, r.display_prefix, r.country_code,
    ST_X(r.centroid) AS lon, ST_Y(r.centroid) AS lat
"""
# Tope de parecidos que se leen: suficientes para desempatar sin traer las
# 296 mil localidades si el nombre es muy común.
MAX_SIMILAR = 50
# Colonias por consulta: una familia grande ("Polanco" tiene 5 secciones) cabe
# de sobra; un nombre muy común en un estado se resuelve como ambiguo.
MAX_NEIGHBORHOODS = 50


def _escape_like(value: str) -> str:
    """Escapa los comodines de LIKE para que el nombre se busque literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _place(row: RowMapping) -> Place:
    level = RegionLevel(row["level"])
    # Igual que Region.display_name: municipios y localidades con su prefijo.
    with_prefix = level in (RegionLevel.MUNICIPALITY, RegionLevel.LOCALITY)
    display = f"{row['display_prefix']} {row['name']}" if with_prefix else row["name"]
    return Place(
        region_id=row["id"],
        code=row["code"],
        level=level,
        name=row["name"],
        display_name=display,
        country_code=row["country_code"],
        lon=row["lon"],
        lat=row["lat"],
    )


class PostgresGazetteer:
    """Búsquedas en ``regions`` por nombre normalizado."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def _fetch(self, sql: str, params: Mapping[str, object]) -> Sequence[RowMapping]:
        async with self._engine.connect() as conn:
            return (await conn.execute(text(sql), dict(params))).mappings().all()

    async def exact(self, name_norm: str) -> list[Place]:
        """Ver ``GazetteerPort.exact``."""
        rows = await self._fetch(
            f"SELECT {_COLUMNS} FROM regions r "  # noqa: S608 — columnas constantes del módulo
            "WHERE r.name_norm = :n OR :n = ANY(r.aliases_norm) ORDER BY r.code",
            {"n": name_norm},
        )
        return [_place(row) for row in rows]

    async def similar(self, name_norm: str, min_similarity: float) -> list[tuple[Place, float]]:
        """Ver ``GazetteerPort.similar``: solo los de la mejor similitud encontrada."""
        rows = await self._fetch(
            f"""
            SELECT {_COLUMNS}, similarity(r.name_norm, :n) AS score
            FROM regions r
            WHERE r.country_code = :mx AND r.name_norm % :n
              AND similarity(r.name_norm, :n) >= :min
            ORDER BY score DESC, r.code
            LIMIT :limit
            """,  # noqa: S608 — columnas constantes del módulo
            {"n": name_norm, "mx": MEXICO_ISO3, "min": min_similarity, "limit": MAX_SIMILAR},
        )
        if not rows:
            return []
        best = rows[0]["score"]
        return [(_place(row), float(row["score"])) for row in rows if row["score"] == best]

    async def country(self, name_norm: str) -> Place | None:
        """Ver ``GazetteerPort.country``."""
        rows = await self._fetch(
            f"SELECT {_COLUMNS} FROM regions r "  # noqa: S608 — columnas constantes del módulo
            "WHERE r.level = 'country' AND (r.name_norm = :n OR :n = ANY(r.aliases_norm)) "
            "ORDER BY r.code LIMIT 1",
            {"n": name_norm},
        )
        return _place(rows[0]) if rows else None

    async def neighborhoods(self, name_core: str, state_code: str) -> list[Neighborhood]:
        """Ver ``GazetteerPort.neighborhoods``."""
        rows = await self._fetch(
            f"""
            SELECT p.name AS p_name, p.name_core AS p_core, p.kind AS p_kind,
                ST_X(p.point) AS p_lon, ST_Y(p.point) AS p_lat,
                {_COLUMNS}
            FROM places p JOIN regions r ON r.id = p.municipality_id
            WHERE (p.name_core = :n OR p.name_core LIKE :family) AND left(r.code, 2) = :state
            ORDER BY (p.name_core = :n) DESC, p.name
            LIMIT :limit
            """,  # noqa: S608 — columnas constantes del módulo
            {
                "n": name_core,
                "family": f"{_escape_like(name_core)} %",
                "state": state_code,
                "limit": MAX_NEIGHBORHOODS,
            },
        )
        return [
            Neighborhood(
                name=row["p_name"],
                name_core=row["p_core"],
                kind=row["p_kind"],
                municipality=_place(row),
                lon=row["p_lon"],
                lat=row["p_lat"],
            )
            for row in rows
        ]

    async def by_code(self, code: str) -> Place | None:
        """Ver ``GazetteerPort.by_code``."""
        rows = await self._fetch(
            f"SELECT {_COLUMNS} FROM regions r WHERE r.code = :c",  # noqa: S608 — columnas constantes
            {"c": code},
        )
        return _place(rows[0]) if rows else None
