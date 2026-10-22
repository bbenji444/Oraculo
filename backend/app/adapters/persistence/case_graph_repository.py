"""``CaseGraphRepositoryPort`` sobre PostgreSQL + PostGIS (Fase 9.6).

Da los puntos que necesita el muro sobre el globo:

- **Lugares:** el punto de la colonia (``places.point``) o el centroide de la
  región (``regions.centroid``) de cada entidad lugar. El punto nunca sale de
  la IA (§11).
- **Notas:** la ubicación principal que ya resolvió el geolocalizador
  (``article_locations.point`` con ``is_primary``), o el centroide de su
  región si la ubicación no trae punto propio.
- **Mis casos:** los casos abiertos de la persona con el centro de sus notas
  ubicadas, las notas y las entidades confirmadas.

No hace: no decide posiciones (``app.domain.case_graph``) ni permisos; solo
lee.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.ports.case_graph import CaseOnMap, GraphPoints, NoteSource
from app.domain.case_graph import GeoPoint

_ENTITY_POINTS_SQL = """
    SELECT e.id, ST_X(pt) AS lon, ST_Y(pt) AS lat
    FROM entities e
    LEFT JOIN places p ON p.id = e.place_id
    LEFT JOIN regions r ON r.id = e.region_id
    CROSS JOIN LATERAL (SELECT COALESCE(p.point, r.centroid) AS pt) x
    WHERE e.id = ANY(:ids) AND e.type = 'place' AND pt IS NOT NULL
"""
# La ubicación principal de cada nota del caso (una por nota; si por algo hay
# dos marcadas, gana la de mayor confianza).
_NOTES_SQL = """
    SELECT a.id, a.title, a.url_canonical, a.published_at,
           ST_X(loc.pt) AS lon, ST_Y(loc.pt) AS lat
    FROM case_articles ca
    JOIN articles a ON a.id = ca.article_id
    LEFT JOIN LATERAL (
        SELECT COALESCE(al.point, r.centroid) AS pt
        FROM article_locations al
        LEFT JOIN regions r ON r.id = al.region_id
        WHERE al.article_id = a.id AND al.is_primary
        ORDER BY al.confidence DESC, al.id
        LIMIT 1
    ) loc ON true
    WHERE ca.case_id = :case
    ORDER BY a.published_at NULLS LAST, a.id
"""
_CASES_ON_MAP_SQL = """
    SELECT c.id, c.name, c.sensitivity,
           (SELECT count(*) FROM case_articles ca WHERE ca.case_id = c.id) AS articles,
           (SELECT count(*) FROM case_entities ce JOIN entities e ON e.id = ce.entity_id
            WHERE ce.case_id = c.id AND e.merged_into IS NULL
              AND e.review_status = 'confirmed') AS confirmed,
           ST_X(center) AS lon, ST_Y(center) AS lat
    FROM cases c
    JOIN case_members cm ON cm.case_id = c.id AND cm.user_id = :user
    CROSS JOIN LATERAL (
        SELECT ST_Centroid(ST_Collect(COALESCE(al.point, r.centroid))) AS center
        FROM case_articles ca
        JOIN article_locations al ON al.article_id = ca.article_id AND al.is_primary
        LEFT JOIN regions r ON r.id = al.region_id
        WHERE ca.case_id = c.id
    ) x
    WHERE c.status = 'open'
"""


def _point(lon: float | None, lat: float | None) -> GeoPoint | None:
    return GeoPoint(float(lon), float(lat)) if lon is not None and lat is not None else None


class PostgresCaseGraphRepository:
    """Puntos del catálogo para dibujar casos sobre el globo."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido de la aplicación.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def points(self, case_id: UUID, entity_ids: list[int]) -> GraphPoints:
        """Ver ``CaseGraphRepositoryPort.points``."""
        async with self._engine.connect() as conn:
            entity_points = {
                int(row["id"]): GeoPoint(float(row["lon"]), float(row["lat"]))
                for row in (
                    await conn.execute(text(_ENTITY_POINTS_SQL), {"ids": entity_ids})
                ).mappings()
            }
            notes = tuple(
                NoteSource(
                    article_id=row["id"],
                    title=row["title"],
                    url=row["url_canonical"],
                    published_at=row["published_at"],
                    point=_point(row["lon"], row["lat"]),
                )
                for row in (await conn.execute(text(_NOTES_SQL), {"case": case_id})).mappings()
            )
        return GraphPoints(entity_points, notes)

    async def cases_on_map(self, user_id: str) -> list[CaseOnMap]:
        """Ver ``CaseGraphRepositoryPort.cases_on_map``."""
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(_CASES_ON_MAP_SQL), {"user": user_id})).mappings()
            return [
                CaseOnMap(
                    case_id=row["id"],
                    name=row["name"],
                    sensitivity=row["sensitivity"],
                    article_count=int(row["articles"]),
                    confirmed_count=int(row["confirmed"]),
                    point=_point(row["lon"], row["lat"]),
                )
                for row in rows
            ]
