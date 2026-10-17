"""Puerto de los proveedores de noticias (especificación §5.2 y §8).

Cada proveedor (SearchApi, GDELT, Google News RSS) tiene un adaptador en
``app/adapters/providers/`` que cumple este contrato. Cambiar de proveedor
es escribir otro adaptador, sin tocar la lógica de negocio.

No hace: no decide presupuesto ni caché (eso es ``ExecuteQueries``).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from app.domain.articles import RawArticle
from app.domain.queries import PlannedQuery, Provider


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Lo que devolvió un proveedor para una consulta.

    Attributes:
        articles: Notas en el formato común, en el orden del proveedor.
        http_status: Código HTTP de la respuesta.
        params: Parámetros enviados, **sin la llave**, para el registro.
        body: Respuesta cruda (texto), para guardarla como fixture.
        discarded: Resultados descartados por inválidos (sin URL o título).
    """

    articles: tuple[RawArticle, ...]
    http_status: int
    params: Mapping[str, str]
    body: str
    discarded: int = 0


class NewsProviderPort(Protocol):
    """Contrato común de los proveedores de noticias."""

    @property
    def provider(self) -> Provider:
        """Qué proveedor es."""
        ...

    def is_configured(self) -> bool:
        """Dice si tiene lo necesario para consultar (por ejemplo, su llave).

        Returns:
            ``False`` si falta configuración: la consulta se salta con aviso.
        """
        ...

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        """Parámetros HTTP que se enviarían para la consulta, sin la llave.

        Args:
            query: Consulta planeada.

        Returns:
            Los parámetros, para mostrarlos y registrarlos.
        """
        ...

    def estimate_cost(self, query: PlannedQuery) -> int:
        """Créditos que costaría la consulta.

        Args:
            query: Consulta planeada.

        Returns:
            Créditos (0 en proveedores gratuitos).
        """
        ...

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        """Ejecuta la consulta.

        Args:
            query: Consulta planeada (de ``build_queries``).

        Returns:
            Las notas normalizadas y los datos de la respuesta.

        Raises:
            ProviderError: Si el proveedor falla tras los reintentos.
        """
        ...
