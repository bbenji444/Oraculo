"""Personas y llaves en PostgreSQL (``users`` y ``access_keys``, ADR-0042).

Implementa ``AccessStorePort``. De cada llave guarda solo su parte pública y
su huella HMAC; nunca la llave completa.

Las lecturas de entrada (``find_key``, ``key_record``, ``mark_key_used``)
corren como ``system`` porque todavía no se sabe quién es la persona. Las de
administración corren con el contexto de la petición: la seguridad por filas
(migración 0039) solo deja pasar a un superusuario.

No hace: no decide si una llave sirve ni quién puede administrar (eso es de
``app.application.use_cases.access``).
"""

import json

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.adapters.persistence.access_scope import as_system
from app.application.audit import AuditEntry
from app.application.ports.access import NewKeyRow, NewUser, UserChanges
from app.domain.access import AuthUser, KeyInfo, KeyRecord, Role, UserAccount
from app.domain.errors import UsernameTakenError

_KEY_RECORD = """
    SELECT k.id, k.key_hash, k.expires_at, k.revoked_at,
           u.id AS user_id, u.username, u.display_name, u.role, u.is_active
    FROM access_keys k JOIN users u ON u.id = k.user_id
"""
_USER_COLUMNS = """
    SELECT u.id, u.username, u.display_name, u.email, u.role, u.is_active, u.created_at,
           u.last_seen_at,
           (SELECT count(*) FROM access_keys k WHERE k.user_id = u.id AND k.revoked_at IS NULL
              AND (k.expires_at IS NULL OR k.expires_at > now())) AS active_keys
    FROM users u
"""
_KEY_COLUMNS = (
    "id, user_id, key_prefix, label, created_by, created_at, expires_at, revoked_at, "
    "last_used_at, host(last_used_ip) AS last_used_ip"
)
# Las columnas son la lista fija de arriba; los valores van como parámetros.
_INSERT_KEY = text(
    "INSERT INTO access_keys (user_id, key_prefix, key_hash, label, created_by, expires_at) "  # noqa: S608 — columnas fijas
    f"VALUES (:u, :p, :h, :l, :by, :x) RETURNING {_KEY_COLUMNS}"
)
_REVOKE_KEY = text(
    "UPDATE access_keys SET revoked_at = coalesce(revoked_at, now()) "  # noqa: S608 — columnas fijas
    f"WHERE id = :id RETURNING {_KEY_COLUMNS}"
)
_AUDIT = text(
    "INSERT INTO audit_log (user_id, action, entity_type, entity_id, payload, ip) "
    "VALUES (:user_id, :action, :entity_type, :entity_id, CAST(:payload AS jsonb), "
    "CAST(:ip AS inet))"
)
# Un uso cada minuto basta para «último uso»: con Bearer, cada petición
# pasaría por aquí y no vale la pena escribir en cada una.
_MARK_USED = text(
    "UPDATE access_keys SET last_used_at = now(), last_used_ip = CAST(:ip AS inet) "
    "WHERE id = :id AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute')"
)
_MARK_SEEN = text(
    "UPDATE users SET last_seen_at = now() "
    "WHERE id = (SELECT user_id FROM access_keys WHERE id = :id) "
    "AND (last_seen_at IS NULL OR last_seen_at < now() - interval '1 minute')"
)


def _record(row: RowMapping) -> KeyRecord:
    return KeyRecord(
        key_id=row["id"],
        key_hash=row["key_hash"],
        user=AuthUser(row["user_id"], row["username"], row["display_name"], Role(row["role"])),
        user_active=row["is_active"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


def _account(row: RowMapping) -> UserAccount:
    return UserAccount(
        user_id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        email=row["email"],
        role=Role(row["role"]),
        is_active=row["is_active"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        active_keys=row["active_keys"],
    )


def _key(row: RowMapping) -> KeyInfo:
    return KeyInfo(
        key_id=row["id"],
        user_id=row["user_id"],
        public_id=row["key_prefix"],
        label=row["label"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        last_used_at=row["last_used_at"],
        last_used_ip=row["last_used_ip"],
    )


async def _audit(conn: AsyncConnection, audit: AuditEntry, entity: str, entity_id: str) -> None:
    await conn.execute(
        _AUDIT,
        {
            "user_id": audit.actor.user_id,
            "action": audit.action,
            "entity_type": entity,
            "entity_id": entity_id,
            "payload": json.dumps(dict(audit.payload), ensure_ascii=False, default=str),
            "ip": audit.actor.ip,
        },
    )


class PostgresAccessStore:
    """``AccessStorePort`` sobre ``users`` y ``access_keys``.

    Args:
        engine: Engine de la API (``create_api_engine``).
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def find_key(self, public_id: str) -> KeyRecord | None:
        """Ver ``AccessStorePort.find_key``."""
        with as_system():
            async with self._engine.connect() as conn:
                row = (
                    (
                        await conn.execute(
                            text(_KEY_RECORD + " WHERE k.key_prefix = :p"), {"p": public_id}
                        )
                    )
                    .mappings()
                    .first()
                )
        return _record(row) if row else None

    async def key_record(self, key_id: int) -> KeyRecord | None:
        """Ver ``AccessStorePort.key_record``."""
        with as_system():
            async with self._engine.connect() as conn:
                row = (
                    (await conn.execute(text(_KEY_RECORD + " WHERE k.id = :id"), {"id": key_id}))
                    .mappings()
                    .first()
                )
        return _record(row) if row else None

    async def mark_key_used(self, key_id: int, ip: str | None) -> None:
        """Ver ``AccessStorePort.mark_key_used``."""
        with as_system():
            async with self._engine.begin() as conn:
                await conn.execute(_MARK_USED, {"id": key_id, "ip": ip})
                await conn.execute(_MARK_SEEN, {"id": key_id})

    async def record_event(self, audit: AuditEntry, entity_id: str) -> None:
        """Ver ``AccessStorePort.record_event``."""
        async with self._engine.begin() as conn:
            await _audit(conn, audit, "access_key", entity_id)

    async def list_users(self) -> list[UserAccount]:
        """Ver ``AccessStorePort.list_users``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(_USER_COLUMNS + " ORDER BY u.is_active DESC, u.role, u.username")
            )
            return [_account(r) for r in rows.mappings()]

    async def get_user(self, user_id: int) -> UserAccount | None:
        """Ver ``AccessStorePort.get_user``."""
        async with self._engine.connect() as conn:
            row = (
                (await conn.execute(text(_USER_COLUMNS + " WHERE u.id = :id"), {"id": user_id}))
                .mappings()
                .first()
            )
        return _account(row) if row else None

    async def active_superusers(self) -> int:
        """Ver ``AccessStorePort.active_superusers``."""
        async with self._engine.connect() as conn:
            value = await conn.scalar(
                text("SELECT count(*) FROM users WHERE role = 'superuser' AND is_active")
            )
        return int(value or 0)

    async def create_user(self, user: NewUser, audit: AuditEntry) -> UserAccount:
        """Ver ``AccessStorePort.create_user``."""
        try:
            async with self._engine.begin() as conn:
                user_id = await conn.scalar(
                    text(
                        "INSERT INTO users (username, display_name, email, role, created_by) "
                        "VALUES (:u, :d, :e, :r, :by) RETURNING id"
                    ),
                    {
                        "u": user.username,
                        "d": user.display_name,
                        "e": user.email,
                        "r": user.role.value,
                        "by": audit.actor.user_id,
                    },
                )
                await _audit(conn, audit, "user", str(user_id))
        except IntegrityError as error:
            raise UsernameTakenError(
                "Ya existe una persona con ese usuario.", {"username": user.username}
            ) from error
        created = await self.get_user(int(user_id))
        if created is None:  # pragma: no cover — se acaba de insertar
            raise UsernameTakenError("No se pudo leer a la persona recién creada.")
        return created

    async def update_user(
        self, user_id: int, changes: UserChanges, audit: AuditEntry
    ) -> UserAccount | None:
        """Ver ``AccessStorePort.update_user``."""
        sets: list[str] = []
        params: dict[str, object] = {"id": user_id}
        if changes.display_name is not None:
            sets.append("display_name = :d")
            params["d"] = changes.display_name
        if changes.email is not None:
            sets.append("email = :e")
            params["e"] = changes.email or None
        if changes.role is not None:
            sets.append("role = :r")
            params["r"] = changes.role.value
        if changes.is_active is not None:
            sets.append("is_active = :a")
            params["a"] = changes.is_active
        if sets:
            async with self._engine.begin() as conn:
                found = await conn.scalar(
                    # Las columnas salen de la lista fija de arriba, no del usuario.
                    text(f"UPDATE users SET {', '.join(sets)} WHERE id = :id RETURNING id"),  # noqa: S608 — columnas fijas
                    params,
                )
                if found is None:
                    return None
                await _audit(conn, audit, "user", str(user_id))
        return await self.get_user(user_id)

    async def user_keys(self, user_id: int) -> list[KeyInfo]:
        """Ver ``AccessStorePort.user_keys``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    f"SELECT {_KEY_COLUMNS} FROM access_keys WHERE user_id = :u "  # noqa: S608 — columnas fijas
                    "ORDER BY created_at DESC, id DESC"
                ),
                {"u": user_id},
            )
            return [_key(r) for r in rows.mappings()]

    async def create_key(self, key: NewKeyRow, audit: AuditEntry) -> KeyInfo:
        """Ver ``AccessStorePort.create_key``."""
        async with self._engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        _INSERT_KEY,
                        {
                            "u": key.user_id,
                            "p": key.public_id,
                            "h": key.key_hash,
                            "l": key.label,
                            "by": audit.actor.user_id,
                            "x": key.expires_at,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await _audit(conn, audit, "access_key", str(row["id"]))
        return _key(row)

    async def revoke_key(self, key_id: int, audit: AuditEntry) -> KeyInfo | None:
        """Ver ``AccessStorePort.revoke_key``."""
        async with self._engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        _REVOKE_KEY,
                        {"id": key_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            await _audit(conn, audit, "access_key", str(key_id))
        return _key(row)
