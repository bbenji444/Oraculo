"""Personas, credenciales y llaves en PostgreSQL (``users``, ``access_keys``).

Implementa ``AccessStorePort`` (ADR-0042 y ADR-0043). Guarda solo huellas: de
cada llave, su parte pública y su huella HMAC; de cada contraseña, su huella
scrypt; del código de 6 dígitos, su secreto cifrado. Nunca nada en claro.

Lo que se usa al entrar (llaves, credenciales, intentos fallidos, alta del
código) corre como ``system``, porque todavía no se sabe quién es la
persona. La administración corre con el contexto de la petición: la
seguridad por filas (migración 0039) solo deja pasar a un superusuario.

No hace: no decide si una llave sirve ni quién puede administrar (eso es de
``app.application.use_cases.access``).
"""

import json
from datetime import datetime

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.adapters.persistence.access_scope import as_system
from app.application.audit import AuditEntry
from app.application.ports.access import NewKeyRow, NewUser, UserChanges, UserCredentials
from app.domain.access import AuthUser, KeyInfo, KeyRecord, Role, UserAccount
from app.domain.errors import UsernameTakenError

_KEY_RECORD = """
    SELECT k.id, k.key_hash, k.expires_at, k.revoked_at,
           u.id AS user_id, u.username, u.display_name, u.role, u.is_active
    FROM access_keys k JOIN users u ON u.id = k.user_id
"""
_USER_COLUMNS = """
    SELECT u.id, u.username, u.display_name, u.email, u.role, u.is_active, u.created_at,
           u.last_seen_at, u.password_hash IS NOT NULL AS has_password,
           u.must_change_password, u.totp_secret IS NOT NULL AS totp_enrolled,
           CASE WHEN u.locked_until > now() THEN u.locked_until END AS locked_until,
           (SELECT count(*) FROM access_keys k WHERE k.user_id = u.id AND k.revoked_at IS NULL
              AND (k.expires_at IS NULL OR k.expires_at > now())) AS active_keys,
           (SELECT k.key_prefix FROM access_keys k WHERE k.user_id = u.id
              AND k.revoked_at IS NULL AND k.secret_sealed IS NOT NULL
              AND (k.expires_at IS NULL OR k.expires_at > now())
              ORDER BY k.created_at DESC, k.id DESC LIMIT 1) AS api_key_prefix
    FROM users u
"""
_CREDENTIALS = """
    SELECT id, username, display_name, role, is_active, password_hash, must_change_password,
           totp_secret, totp_last_counter, failed_logins, locked_until
    FROM users
"""
# Las personas borradas (borrado lógico, migración 0041) no existen para nadie:
# ni para entrar ni en «Accesos».
_ALIVE = "deleted_at IS NULL"
# Guarda los fallos seguidos (los calcula el caso de uso) y, con :lock, el
# bloqueo; sin :lock se borra un bloqueo que ya venció.
_LOGIN_FAILED = text(
    "UPDATE users SET failed_logins = :n, locked_until = CAST(:lock AS timestamptz) WHERE id = :id"
)
_LOGIN_OK = text(
    "UPDATE users SET failed_logins = 0, locked_until = NULL, last_seen_at = now() WHERE id = :id"
)
_SET_PASSWORD = text(
    "UPDATE users SET password_hash = :h, must_change_password = :must, "
    "password_changed_at = now(), failed_logins = 0, locked_until = NULL WHERE id = :id"
)
_SET_TOTP = text(
    "UPDATE users SET totp_secret = CAST(:s AS text), totp_last_counter = NULL, "
    "totp_enrolled_at = CASE WHEN CAST(:s AS text) IS NULL THEN NULL ELSE now() END "
    "WHERE id = :id"
)
# Atómico: solo avanza si el periodo es más nuevo que el último usado, así un
# mismo código no sirve dos veces aunque lleguen dos peticiones a la vez.
_USE_COUNTER = text(
    "UPDATE users SET totp_last_counter = :c "
    "WHERE id = :id AND (totp_last_counter IS NULL OR totp_last_counter < :c) RETURNING id"
)
# Borrado lógico: se quitan contraseña y código para que una cuenta borrada
# no pueda volver a usarse aunque alguien la «reviviera» a mano.
_DELETE_USER = text(
    "UPDATE users SET deleted_at = now(), is_active = false, password_hash = NULL, "
    "totp_secret = NULL, totp_last_counter = NULL, must_change_password = true "
    "WHERE id = :id AND deleted_at IS NULL RETURNING username"
)
# Sus envíos programados se apagan (no se borran): una persona borrada no
# debe seguir mandando reportes. Benji, 11/11/2026: «pp» seguía prendido.
_PAUSE_USER_SCHEDULES = text(
    "UPDATE delivery_schedules SET is_active = false, updated_at = now() "
    "WHERE owner = :owner AND is_active RETURNING id"
)
_REVOKE_USER_KEYS = text(
    "UPDATE access_keys SET revoked_at = now() WHERE user_id = :id AND revoked_at IS NULL"
)
_KEY_COLUMNS = (
    "id, user_id, key_prefix, label, created_by, created_at, expires_at, revoked_at, "
    "last_used_at, host(last_used_ip) AS last_used_ip, secret_sealed IS NOT NULL AS revealable"
)
# Las columnas son la lista fija de arriba; los valores van como parámetros.
_INSERT_KEY = text(
    "INSERT INTO access_keys (user_id, key_prefix, key_hash, label, created_by, expires_at, "  # noqa: S608 — columnas fijas
    f"secret_sealed) VALUES (:u, :p, :h, :l, :by, :x, :sealed) RETURNING {_KEY_COLUMNS}"
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
        has_password=row["has_password"],
        must_change_password=row["must_change_password"],
        totp_enrolled=row["totp_enrolled"],
        locked_until=row["locked_until"],
        api_key_prefix=row["api_key_prefix"],
    )


def _credentials(row: RowMapping) -> UserCredentials:
    return UserCredentials(
        user=AuthUser(row["id"], row["username"], row["display_name"], Role(row["role"])),
        is_active=row["is_active"],
        password_hash=row["password_hash"],
        must_change_password=row["must_change_password"],
        totp_secret=row["totp_secret"],
        totp_last_counter=row["totp_last_counter"],
        failed_logins=row["failed_logins"],
        locked_until=row["locked_until"],
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
        revealable=row["revealable"],
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

    async def _one_credentials(self, where: str, value: object) -> UserCredentials | None:
        with as_system():
            async with self._engine.connect() as conn:
                row = (
                    (
                        await conn.execute(
                            text(f"{_CREDENTIALS} WHERE {where} = :v AND {_ALIVE}"), {"v": value}
                        )
                    )
                    .mappings()
                    .first()
                )
        return _credentials(row) if row else None

    async def find_credentials(self, username: str) -> UserCredentials | None:
        """Ver ``AccessStorePort.find_credentials``."""
        return await self._one_credentials("username", username)

    async def credentials(self, user_id: int) -> UserCredentials | None:
        """Ver ``AccessStorePort.credentials``."""
        return await self._one_credentials("id", user_id)

    async def login_failed(
        self, user_id: int, failures: int, locked_until: datetime | None
    ) -> None:
        """Ver ``AccessStorePort.login_failed``."""
        with as_system():
            async with self._engine.begin() as conn:
                await conn.execute(
                    _LOGIN_FAILED, {"id": user_id, "n": failures, "lock": locked_until}
                )

    async def login_succeeded(self, user_id: int, ip: str | None) -> None:
        """Ver ``AccessStorePort.login_succeeded``."""
        with as_system():
            async with self._engine.begin() as conn:
                await conn.execute(_LOGIN_OK, {"id": user_id})

    async def set_password(
        self, user_id: int, password_hash: str, must_change: bool, audit: AuditEntry
    ) -> None:
        """Ver ``AccessStorePort.set_password``."""
        with as_system():
            async with self._engine.begin() as conn:
                await conn.execute(
                    _SET_PASSWORD, {"id": user_id, "h": password_hash, "must": must_change}
                )
                await _audit(conn, audit, "user", str(user_id))

    async def set_totp(self, user_id: int, secret: str | None, audit: AuditEntry) -> None:
        """Ver ``AccessStorePort.set_totp``."""
        with as_system():
            async with self._engine.begin() as conn:
                await conn.execute(_SET_TOTP, {"id": user_id, "s": secret})
                await _audit(conn, audit, "user", str(user_id))

    async def use_totp_counter(self, user_id: int, counter: int) -> bool:
        """Ver ``AccessStorePort.use_totp_counter``."""
        with as_system():
            async with self._engine.begin() as conn:
                used = await conn.scalar(_USE_COUNTER, {"id": user_id, "c": counter})
        return used is not None

    async def delete_user(self, user_id: int, audit: AuditEntry) -> bool:
        """Ver ``AccessStorePort.delete_user``."""
        async with self._engine.begin() as conn:
            username = await conn.scalar(_DELETE_USER, {"id": user_id})
            if username is None:
                return False
            await conn.execute(_REVOKE_USER_KEYS, {"id": user_id})
            paused = (await conn.execute(_PAUSE_USER_SCHEDULES, {"owner": username})).scalars()
            # La bitácora dice qué envíos se apagaron con el borrado.
            payload = {**audit.payload, "envios_apagados": sorted(paused)}
            await _audit(conn, AuditEntry(audit.actor, audit.action, payload), "user", str(user_id))
        return True

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
                text(
                    _USER_COLUMNS
                    + " WHERE u.deleted_at IS NULL ORDER BY u.is_active DESC, u.role, u.username"
                )
            )
            return [_account(r) for r in rows.mappings()]

    async def get_user(self, user_id: int) -> UserAccount | None:
        """Ver ``AccessStorePort.get_user``."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(_USER_COLUMNS + " WHERE u.id = :id AND u.deleted_at IS NULL"),
                        {"id": user_id},
                    )
                )
                .mappings()
                .first()
            )
        return _account(row) if row else None

    async def active_superusers(self) -> int:
        """Ver ``AccessStorePort.active_superusers``."""
        async with self._engine.connect() as conn:
            value = await conn.scalar(
                text(
                    "SELECT count(*) FROM users "
                    "WHERE role = 'superuser' AND is_active AND deleted_at IS NULL"
                )
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
                "Ese usuario ya existe o existió (los usuarios borrados quedan reservados).",
                {"username": user.username},
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
                            "sealed": key.secret_sealed,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await _audit(conn, audit, "access_key", str(row["id"]))
        return _key(row)

    async def api_key(self, user_id: int) -> tuple[KeyInfo, str] | None:
        """Ver ``AccessStorePort.api_key``."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            f"SELECT {_KEY_COLUMNS}, secret_sealed FROM access_keys "  # noqa: S608 — columnas fijas
                            "WHERE user_id = :u AND revoked_at IS NULL "
                            "AND secret_sealed IS NOT NULL "
                            "AND (expires_at IS NULL OR expires_at > now()) "
                            "ORDER BY created_at DESC, id DESC LIMIT 1"
                        ),
                        {"u": user_id},
                    )
                )
                .mappings()
                .first()
            )
        return (_key(row), str(row["secret_sealed"])) if row else None

    async def totp_required(self) -> bool:
        """Ver ``AccessStorePort.totp_required``."""
        # Se lee antes de saber quién entra: como el sistema.
        with as_system():
            async with self._engine.connect() as conn:
                value = await conn.scalar(
                    text("SELECT totp_required FROM auth_settings WHERE id = 1")
                )
        # Sin la fila (base sin la migración 0044) se pide el código, como antes.
        return True if value is None else bool(value)

    async def set_totp_required(self, required: bool, audit: AuditEntry) -> None:
        """Ver ``AccessStorePort.set_totp_required``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO auth_settings (id, totp_required, updated_at, updated_by) "
                    "VALUES (1, :v, now(), :by) ON CONFLICT (id) DO UPDATE SET "
                    "totp_required = EXCLUDED.totp_required, updated_at = now(), "
                    "updated_by = EXCLUDED.updated_by"
                ),
                {"v": required, "by": audit.actor.user_id},
            )
            await _audit(conn, audit, "auth_settings", "1")

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
