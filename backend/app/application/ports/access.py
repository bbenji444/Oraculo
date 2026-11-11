"""Puertos del acceso al monitor (ADR-0042 y ADR-0043).

- ``AccessStorePort``: personas, contraseñas, códigos de 6 dígitos y llaves en
  PostgreSQL (solo huellas y secretos cifrados).
- ``SessionStorePort``: sesiones (el «token interno») en Redis.
- ``LoginTicketStorePort``: el paso a paso de entrar (contraseña → código).
- ``LoginLimiterPort``: cuenta intentos fallidos por IP.
- ``SecretBoxPort``: cifra el secreto del código de 6 dígitos.
- ``QrRendererPort``: dibuja el código QR para Microsoft Authenticator.

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
    """Una sesión abierta (el token interno de la persona).

    Attributes:
        user: La persona (se refresca al revisar).
        key_id: Con qué llave entró, o ``None`` si entró con contraseña y código.
        created_at: Cuándo entró (para el tope absoluto).
        checked_at: Última revisión en la base.
    """

    user: AuthUser
    key_id: int | None
    created_at: datetime
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class UserCredentials:
    """Lo que se necesita para revisar la contraseña y el código de alguien.

    Attributes:
        user: La persona.
        is_active: Si puede entrar.
        password_hash: Huella scrypt, o ``None`` si nunca se le dio contraseña.
        must_change_password: Si su contraseña es temporal.
        totp_secret: Secreto del código de 6 dígitos, **cifrado**; ``None`` si
            todavía no da de alta su Authenticator.
        totp_last_counter: Último periodo de código usado (anti-repetición).
        failed_logins: Intentos fallidos seguidos.
        locked_until: Hasta cuándo está bloqueada por intentos fallidos.
    """

    user: AuthUser
    is_active: bool
    password_hash: str | None
    must_change_password: bool
    totp_secret: str | None
    totp_last_counter: int | None
    failed_logins: int
    locked_until: datetime | None


@dataclass(frozen=True, slots=True)
class LoginTicket:
    """Un ingreso a medias: ya pasó la contraseña, falta el código o el alta.

    Attributes:
        user_id: La persona.
        username: Su usuario.
        must_change_password: Debe cambiar su contraseña temporal antes.
        needs_enrollment: Debe dar de alta su Authenticator antes.
        pending_secret: Secreto nuevo **cifrado**, mientras da de alta su app.
        attempts: Códigos equivocados en este ingreso.
    """

    user_id: int
    username: str
    must_change_password: bool
    needs_enrollment: bool
    pending_secret: str | None = None
    attempts: int = 0


class AccessStorePort(Protocol):
    """Personas, contraseñas, códigos y llaves."""

    async def find_credentials(self, username: str) -> UserCredentials | None:
        """Credenciales por usuario (para entrar), o ``None``."""
        ...

    async def credentials(self, user_id: int) -> UserCredentials | None:
        """Credenciales por id (pasos siguientes y revisión de la sesión)."""
        ...

    async def login_failed(
        self, user_id: int, failures: int, locked_until: datetime | None
    ) -> None:
        """Guarda cuántos fallos seguidos lleva y, si se da, bloquea hasta esa hora."""
        ...

    async def login_succeeded(self, user_id: int, ip: str | None) -> None:
        """Borra los fallos y anota la última entrada."""
        ...

    async def set_password(
        self, user_id: int, password_hash: str, must_change: bool, audit: AuditEntry
    ) -> None:
        """Guarda la huella de una contraseña nueva (y si es temporal)."""
        ...

    async def set_totp(self, user_id: int, secret: str | None, audit: AuditEntry) -> None:
        """Guarda el secreto cifrado del código, o lo borra con ``None``."""
        ...

    async def use_totp_counter(self, user_id: int, counter: int) -> bool:
        """Marca un periodo de código como usado; ``False`` si ya se había usado."""
        ...

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


class LoginTicketStorePort(Protocol):
    """Ingresos a medias (entre la contraseña y el código)."""

    async def create(self, ticket: LoginTicket, ttl_seconds: int) -> str:
        """Guarda el ingreso y devuelve el valor que viaja al navegador."""
        ...

    async def get(self, token: str) -> LoginTicket | None:
        """El ingreso, o ``None`` si no existe o ya venció."""
        ...

    async def save(self, token: str, ticket: LoginTicket, ttl_seconds: int) -> None:
        """Actualiza el ingreso."""
        ...

    async def delete(self, token: str) -> None:
        """Lo borra (al terminar o al fallar demasiadas veces)."""
        ...


class SecretBoxPort(Protocol):
    """Cifra y descifra textos cortos con el secreto del servidor."""

    def seal(self, plain: str) -> str:
        """Texto cifrado y autenticado (nadie lo puede leer ni alterar)."""
        ...

    def open(self, sealed: str) -> str:
        """El texto original.

        Raises:
            ValueError: Si el texto fue alterado o se cifró con otra pimienta.
        """
        ...


class QrRendererPort(Protocol):
    """Dibuja un código QR."""

    def svg(self, content: str) -> str:
        """El QR como imagen SVG (texto)."""
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
