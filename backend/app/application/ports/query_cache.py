"""Puerto de la caché de consultas (especificación §7.2).

Una consulta idéntica (proveedor + texto + parámetros) dentro de
``QUERY_CACHE_TTL_HOURS`` no vuelve a enviarse ni a gastar créditos. Lo
implementa Redis (``adapters/cache``); las pruebas usan uno en memoria.

No hace: no decide cuándo usar la caché (eso es ``ExecuteQueries``).
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Protocol

from app.domain.articles import RawArticle


def cache_key(provider: str, text: str, params: Mapping[str, str]) -> str:
    """Huella de una consulta: misma huella = misma consulta.

    Los parámetros se ordenan para que el orden en que se arman no cambie la
    huella. Nunca incluyen la llave del proveedor (van en encabezados).

    Args:
        provider: Proveedor.
        text: Texto exacto.
        params: Parámetros HTTP sin la llave.

    Returns:
        Huella SHA-256 en hexadecimal.
    """
    canonical = json.dumps(
        {"provider": provider, "text": text, "params": dict(sorted(params.items()))},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class QueryCachePort(Protocol):
    """Lectura y escritura de resultados de consultas."""

    async def get(self, key: str) -> tuple[RawArticle, ...] | None:
        """Resultados guardados para una huella.

        Args:
            key: Huella de ``cache_key``.

        Returns:
            Las notas, o ``None`` si no hay nada vigente.
        """
        ...

    async def set(self, key: str, articles: tuple[RawArticle, ...], ttl_seconds: int) -> None:
        """Guarda los resultados de una consulta.

        Args:
            key: Huella de ``cache_key``.
            articles: Notas normalizadas.
            ttl_seconds: Segundos que duran vigentes.
        """
        ...
