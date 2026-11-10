"""Puertos del acceso con llave (ADR-0042).

- ``AccessStorePort``: personas y llaves en PostgreSQL (solo huellas).
- ``SessionStorePort``: sesiones del navegador en Redis.
- ``LoginLimiterPort``: cuenta intentos fallidos por IP.

Los usan los casos de uso de ``app.application.use_cases.access``.
No hace: no sabe de cookies ni de HTTP.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.application.audit import AuditEntry
from app.domain.access import AuthUser, KeyInfo, KeyRecord, Role, UserAccount


@dataclass(frozen=True, slots=True)
class NewUser:
    """Datos de una persona nueva (ya validados).

    Attributes:
        username: Identificador.
        display_name: Nombre para mostrar.
        email: Correo, opcional.
        role: Rol.
    """

    username: str
    display_name: str
    email: str | None
    role: Role


@dataclass(frozen=True, slots=True)
class UserChanges:
    """Lo que se cambia de una persona; ``None`` = no se toca.

    Attributes:
        display_name: Nombre nuevo.
        email: Correo nuevo (``""`` lo borra).
        role: Rol nuevo.
        is_active: Activar o desactivar.
    """

    display_name: str | None = None
    email: str | None = None
    role: Role | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class NewKeyRow:
    """Una llave para guardar: solo su parte pública y su huella.

    Attributes:
        user_id: Dueño.
        public_id: Parte pública.
        key_hash: Huella HMAC.
        label: Para qué es.
        expires_at: Vencimiento.
    """

    user_id: int
    public_id: str
    key_hash: str
    label: str
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class SessionData:
    """Una sesión abierta del navegador.

    Attributes:
        user: La persona (se refresca al revisar).
        key_id: Con qué llave entró.
        created_at: Cuándo entró (para el tope absoluto).
        checked_at: Última revisión en la base.
    """

    user: AuthUser
    key_id: int
    created_at: datetime
    checked_at: datetime


class AccessStorePort(Protocol):
    """Personas y llaves."""

    async def find_key(self, public_id: str) -> KeyRecord | None:
        """La llave con esa parte pública y su dueño, o ``None``."""
        ...

    async def key_record(self, key_id: int) -> KeyRecord | None:
        """La llave por id (para revisar una sesión abierta)."""
        ...

    async def mark_key_used(self, key_id: int, ip: str | None) -> None:
        """Anota último uso de la llave y última entrada de su dueño."""
        ...

    async def record_event(self, audit: AuditEntry, entity_id: str) -> None:
        """Deja en la bitácora una entrada o un intento fallido."""
        ...

    async def list_users(self) -> list[UserAccount]:
        """Todas las personas, con cuántas llaves vigentes tiene cada una."""
        ...

    async def get_user(self, user_id: int) -> UserAccount | None:
        """Una persona."""
        ...

    async def active_superusers(self) -> int:
        """Cuántos superusuarios activos hay."""
        ...

    async def create_user(self, user: NewUser, audit: AuditEntry) -> UserAccount:
        """Da de alta a una persona.

        Raises:
            UsernameTakenError: Si el usuario ya existe.
        """
        ...

    async def update_user(
        self, user_id: int, changes: UserChanges, audit: AuditEntry
    ) -> UserAccount | None:
        """Aplica los cambios; ``None`` si no existe."""
        ...

    async def user_keys(self, user_id: int) -> list[KeyInfo]:
        """Las llaves de una persona, la más nueva primero."""
        ...

    async def create_key(self, key: NewKeyRow, audit: AuditEntry) -> KeyInfo:
        """Guarda la huella de una llave nueva."""
        ...

    async def revoke_key(self, key_id: int, audit: AuditEntry) -> KeyInfo | None:
        """Revoca la llave (si ya lo estaba, no cambia); ``None`` si no existe."""
        ...


class SessionStorePort(Protocol):
    """Sesiones del navegador."""

    async def create(self, data: SessionData, idle_seconds: int, max_seconds: int) -> str:
        """Abre una sesión y devuelve el valor para la cookie."""
        ...

    async def get(self, token: str, idle_seconds: int) -> SessionData | None:
        """La sesión (y la mantiene viva otro rato), o ``None``."""
        ...

    async def save(self, token: str, data: SessionData, idle_seconds: int) -> None:
        """Guarda la sesión revisada."""
        ...

    async def delete(self, token: str) -> None:
        """Cierra una sesión."""
        ...

    async def delete_for_user(self, user_id: int, key_id: int | None = None) -> int:
        """Cierra las sesiones de una persona (solo las de esa llave, si se da).

        Returns:
            Cuántas se cerraron.
        """
        ...


class LoginLimiterPort(Protocol):
    """Freno de intentos fallidos por IP."""

    async def blocked(self, ip: str | None) -> bool:
        """Si esa IP ya pasó el tope de intentos en la ventana."""
        ...

    async def failure(self, ip: str | None) -> None:
        """Suma un intento fallido."""
        ...

    async def clear(self, ip: str | None) -> None:
        """Borra la cuenta (al entrar bien)."""
        ...
