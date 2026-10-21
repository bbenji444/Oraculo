"""Puerto del catálogo para el geolocalizador (§11).

La implementación (``app/adapters/persistence/gazetteer_repository.py``)
consulta ``regions``; las pruebas usan un catálogo en memoria.

No hace: no decide nada (las reglas están en ``app.domain.geocoding``).
"""

from typing import Protocol

from app.domain.geocoding import Neighborhood, Place


class GazetteerPort(Protocol):
    """Búsquedas en el catálogo de regiones por nombre normalizado."""

    async def exact(self, name_norm: str) -> list[Place]:
        """Regiones cuyo nombre o alias normalizado es exactamente ese.

        Args:
            name_norm: Nombre normalizado (``normalize_name``).

        Returns:
            Todas las coincidencias, de cualquier nivel y país.
        """
        ...

    async def similar(self, name_norm: str, min_similarity: float) -> list[tuple[Place, float]]:
        """Regiones de México con nombre parecido (trigramas), de la más parecida a la menos.

        Args:
            name_norm: Nombre normalizado.
            min_similarity: Similitud mínima (0 a 1).

        Returns:
            Pares (región, similitud), solo con la mejor similitud encontrada.
        """
        ...

    async def country(self, name_norm: str) -> Place | None:
        """El país con ese nombre o alias normalizado.

        Args:
            name_norm: Nombre normalizado ("ESPAÑA").

        Returns:
            El país, o ``None``.
        """
        ...

    async def neighborhoods(self, name_core: str, state_code: str) -> list[Neighborhood]:
        """Colonias de OpenStreetMap de un estado con ese nombre o de su familia.

        Args:
            name_core: Nombre normalizado sin palabra genérica ("POLANCO").
            state_code: Clave INEGI del estado ("09").

        Returns:
            Las de nombre exacto y las que empiezan con ese nombre seguido de
            otra palabra ("POLANCO 1ª SECCION"), con su municipio.
        """
        ...

    async def by_code(self, code: str) -> Place | None:
        """La región con esa clave.

        Args:
            code: Clave INEGI o ISO-A3.

        Returns:
            La región, o ``None``.
        """
        ...
