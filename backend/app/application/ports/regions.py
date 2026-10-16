"""Puerto de consulta del catálogo de regiones.

Lo implementa el repositorio de PostgreSQL (``adapters/persistence``). Los
casos de uso de ``application/use_cases/regions.py`` lo reciben sin saber
de SQL; las pruebas usan uno falso en memoria.

No hace: no modifica el catálogo (eso lo hace el pipeline de geodatos).
"""

from typing import Protocol

from app.application.pagination import NameCursor
from app.domain.queries import PlaceFacts
from app.domain.region import GeoPoint, Region, RegionLevel, RegionRef


class RegionRepositoryPort(Protocol):
    """Consultas de solo lectura sobre ``regions``."""

    async def list_by_level(
        self, level: RegionLevel, after: NameCursor | None, limit: int
    ) -> list[Region]:
        """Regiones de un nivel en orden alfabético, después del cursor.

        Args:
            level: Nivel a listar.
            after: Posición desde la cual seguir, o ``None`` para empezar.
            limit: Máximo de registros.

        Returns:
            Hasta ``limit`` regiones ordenadas por (``name_norm``, ``id``).
        """
        ...

    async def list_children(
        self, parent_id: int, after: NameCursor | None, limit: int
    ) -> list[Region]:
        """Hijas directas de una región, en orden alfabético.

        Args:
            parent_id: Región padre.
            after: Posición desde la cual seguir.
            limit: Máximo de registros.

        Returns:
            Hasta ``limit`` regiones hijas.
        """
        ...

    async def get(self, region_id: int) -> Region | None:
        """Busca una región por id.

        Args:
            region_id: Identificador.

        Returns:
            La región, o ``None`` si no existe.
        """
        ...

    async def ancestors(self, region_id: int) -> list[RegionRef]:
        """Ancestros de una región, del más general al más cercano.

        Args:
            region_id: Identificador.

        Returns:
            Por ejemplo [México, Ciudad de México] para Iztapalapa.
        """
        ...

    async def search(self, query_norm: str, limit: int) -> list[Region]:
        """Búsqueda difusa por nombre o alias ya normalizado.

        Args:
            query_norm: Texto normalizado con ``normalize_name``.
            limit: Máximo de resultados.

        Returns:
            Las mejores coincidencias, de la más a la menos relevante.
        """
        ...

    async def place_facts(self, region_id: int) -> PlaceFacts | None:
        """Datos de la región que importan para armar consultas (ADR-0009).

        Args:
            region_id: Identificador.

        Returns:
            Nombre, términos curados, si el nombre se repite en su nivel,
            su estado y su país; ``None`` si la región no existe.
        """
        ...

    async def find_at_point(self, point: GeoPoint, level: RegionLevel | None) -> Region | None:
        """Región que contiene un punto.

        Args:
            point: Punto a ubicar.
            level: Nivel buscado; ``None`` para la más específica.

        Returns:
            La región, o ``None`` si ninguna contiene el punto.
        """
        ...
