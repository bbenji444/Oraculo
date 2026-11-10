"""Sesiones del navegador y freno de intentos, en Redis (ADR-0042).

- ``RedisSessionStore``: cada sesión es una llave ``monitor:sesion:<huella>``
  que se borra sola tras el tiempo sin uso. Se guarda la **huella** SHA-256
  del valor de la cookie, no el valor: quien lea Redis no puede usarla. Un
  conjunto ``monitor:sesiones:<user_id>`` permite cerrar de golpe las de
  una persona (al revocar o desactivar).
- ``RedisLoginLimiter``: cuenta fallos por IP en una ventana fija.

No hace: no decide si una llave sirve (eso es de los casos de uso).
"""

import inspect
import json
from collections.abc import Awaitable
from datetime import datetime

from redis.asyncio import Redis

from app.application.ports.access import SessionData
from app.domain.access import AuthUser, Role, new_session_token, session_digest

_SESSION = "monitor:sesion:"
_USER_SESSIONS = "monitor:sesiones:"
_FAILURES = "monitor:fallos-llave:"


async def _awaited[T](value: Awaitable[T] | T) -> T:
    # redis-py tipa los comandos de conjuntos como «awaitable o valor» (sirve
    # para el cliente síncrono y el asíncrono); con el asíncrono es awaitable.
    if inspect.isawaitable(value):
        return await value
    return value


def _encode(data: SessionData) -> str:
    return json.dumps(
        {
            "user_id": data.user.user_id,
            "username": data.user.username,
            "display_name": data.user.display_name,
            "role": data.user.role.value,
            "key_id": data.key_id,
            "created_at": data.created_at.isoformat(),
            "checked_at": data.checked_at.isoformat(),
        }
    )


def _decode(raw: bytes | str) -> SessionData:
    value = json.loads(raw)
    return SessionData(
        user=AuthUser(
            value["user_id"], value["username"], value["display_name"], Role(value["role"])
        ),
        key_id=value["key_id"],
        created_at=datetime.fromisoformat(value["created_at"]),
        checked_at=datetime.fromisoformat(value["checked_at"]),
    )


class RedisSessionStore:
    """``SessionStorePort`` sobre Redis.

    Args:
        client: Cliente de Redis compartido.
    """

    def __init__(self, client: Redis) -> None:
        self._redis = client

    async def create(self, data: SessionData, idle_seconds: int, max_seconds: int) -> str:
        """Ver ``SessionStorePort.create``."""
        token = new_session_token()
        digest = session_digest(token)
        index = f"{_USER_SESSIONS}{data.user.user_id}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(f"{_SESSION}{digest}", _encode(data), ex=idle_seconds)
            pipe.sadd(index, digest)
            pipe.expire(index, max_seconds)
            await pipe.execute()
        return token

    async def get(self, token: str, idle_seconds: int) -> SessionData | None:
        """Ver ``SessionStorePort.get``."""
        name = f"{_SESSION}{session_digest(token)}"
        # GETEX lee y renueva el tiempo sin uso en un solo paso.
        raw = await self._redis.getex(name, ex=idle_seconds)
        return _decode(raw) if raw else None

    async def save(self, token: str, data: SessionData, idle_seconds: int) -> None:
        """Ver ``SessionStorePort.save``."""
        await self._redis.set(f"{_SESSION}{session_digest(token)}", _encode(data), ex=idle_seconds)

    async def delete(self, token: str) -> None:
        """Ver ``SessionStorePort.delete``."""
        await self._redis.delete(f"{_SESSION}{session_digest(token)}")

    async def delete_for_user(self, user_id: int, key_id: int | None = None) -> int:
        """Ver ``SessionStorePort.delete_for_user``."""
        index = f"{_USER_SESSIONS}{user_id}"
        closed = 0
        for member in await _awaited(self._redis.smembers(index)):
            digest = member.decode() if isinstance(member, bytes) else str(member)
            name = f"{_SESSION}{digest}"
            raw = await self._redis.get(name)
            if raw is None:
                await _awaited(self._redis.srem(index, digest))
                continue
            if key_id is not None and _decode(raw).key_id != key_id:
                continue
            closed += int(await self._redis.delete(name))
            await _awaited(self._redis.srem(index, digest))
        return closed


class RedisLoginLimiter:
    """``LoginLimiterPort`` sobre Redis: ventana fija por IP.

    Args:
        client: Cliente de Redis compartido.
        max_failures: Fallos que bloquean.
        window_seconds: Duración de la ventana.
    """

    def __init__(self, client: Redis, max_failures: int, window_seconds: int) -> None:
        self._redis = client
        self._max = max_failures
        self._window = window_seconds

    @staticmethod
    def _name(ip: str | None) -> str:
        # Sin IP (no debería pasar detrás de nginx) todos comparten la cuenta.
        return f"{_FAILURES}{ip or 'sin-ip'}"

    async def blocked(self, ip: str | None) -> bool:
        """Ver ``LoginLimiterPort.blocked``."""
        value = await self._redis.get(self._name(ip))
        return value is not None and int(value) >= self._max

    async def failure(self, ip: str | None) -> None:
        """Ver ``LoginLimiterPort.failure``."""
        name = self._name(ip)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(name)
            # NX: la ventana empieza con el primer fallo y no se alarga.
            pipe.expire(name, self._window, nx=True)
            await pipe.execute()

    async def clear(self, ip: str | None) -> None:
        """Ver ``LoginLimiterPort.clear``."""
        await self._redis.delete(self._name(ip))
