"""Caché de consultas a proveedores sobre Redis (especificación §7.2).

Cada consulta se guarda como JSON bajo ``mn:query:<huella>`` con tiempo de
vida (``QUERY_CACHE_TTL_HOURS``). Redis la borra solo al vencer.

Si Redis falla, la búsqueda no se cae: leer devuelve "no hay" y guardar se
omite, con una advertencia en el registro. Se pierde el ahorro, no la búsqueda.

No hace: no decide cuándo usar la caché.
"""

import json
import logging
from datetime import datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.domain.articles import RawArticle
from app.domain.queries import Provider

logger = logging.getLogger(__name__)

KEY_PREFIX = "mn:query:"


def to_json(articles: tuple[RawArticle, ...]) -> str:
    """Serializa notas a JSON.

    Args:
        articles: Notas normalizadas.

    Returns:
        Texto JSON.
    """
    return json.dumps(
        [
            {
                "provider": a.provider.value,
                "provider_rank": a.provider_rank,
                "url": a.url,
                "title": a.title,
                "source_name": a.source_name,
                "source_domain": a.source_domain,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "snippet": a.snippet,
                "language": a.language,
                "raw": dict(a.raw),
            }
            for a in articles
        ],
        ensure_ascii=False,
    )


def from_json(text: str) -> tuple[RawArticle, ...]:
    """Reconstruye las notas guardadas.

    Args:
        text: JSON de ``to_json``.

    Returns:
        Las notas, validadas otra vez con ``RawArticle.create``.
    """
    items: list[dict[str, Any]] = json.loads(text)
    return tuple(
        RawArticle.create(
            provider=Provider(item["provider"]),
            provider_rank=item["provider_rank"],
            url=item["url"],
            title=item["title"],
            source_name=item["source_name"],
            source_domain=item["source_domain"],
            published_at=(
                datetime.fromisoformat(item["published_at"]) if item["published_at"] else None
            ),
            snippet=item["snippet"],
            language=item["language"],
            raw=item["raw"],
        )
        for item in items
    )


class RedisQueryCache:
    """``QueryCachePort`` sobre Redis."""

    def __init__(self, client: Redis) -> None:
        """Recibe el cliente de Redis compartido.

        Args:
            client: Cliente asíncrono de Redis.
        """
        self._client = client

    async def get(self, key: str) -> tuple[RawArticle, ...] | None:
        """Ver ``QueryCachePort.get``."""
        try:
            value = await self._client.get(KEY_PREFIX + key)
        except RedisError as error:
            logger.warning(f"Caché de consultas no disponible al leer: {error}")
            return None
        if value is None:
            return None
        text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        return from_json(text)

    async def set(self, key: str, articles: tuple[RawArticle, ...], ttl_seconds: int) -> None:
        """Ver ``QueryCachePort.set``. Con ``ttl_seconds`` 0 no guarda nada."""
        if ttl_seconds <= 0:
            return
        try:
            await self._client.set(KEY_PREFIX + key, to_json(articles), ex=ttl_seconds)
        except RedisError as error:
            logger.warning(f"Caché de consultas no disponible al guardar: {error}")
