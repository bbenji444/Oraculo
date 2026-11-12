"""Casos de uso del acceso al monitor (ADR-0042 y ADR-0043).

- ``Authenticator``: reconocer en cada petición la sesión (el token interno
  que se abre al entrar con contraseña y código, ver ``login.py``) o una
  llave ``Bearer`` de un sistema; salir; y decirle a otro módulo de quién es
  un token (``introspect``).
- ``AccessAdmin``: lo que hace el superusuario en «Accesos»: dar de alta
  personas con contraseña temporal, cambiar su rol o desactivarlas,
  restablecer su contraseña o su Authenticator, y crear y revocar llaves.

Reglas de seguridad:

- el mismo mensaje para llave inexistente, revocada, vencida o de alguien
  desactivado (no se da pista de cuáles existen);
- 10 fallos por IP en 15 min bloquean esa IP un rato;
- revocar una llave o desactivar a alguien cierra sus sesiones al instante,
  y cada sesión vuelve a revisar la base cada 5 min;
- nadie se quita a sí mismo el rol ni se desactiva, y siempre queda al
  menos un superusuario activo.

No hace: no sabe de cookies ni de HTTP (eso es de ``app.api``).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from app.application.audit import Actor, AuditEntry
from app.application.ports.access import (
    AccessStorePort,
    LoginLimiterPort,
    NewKeyRow,
    NewUser,
    SecretBoxPort,
    SessionData,
    SessionStorePort,
    UserChanges,
)
from app.domain.access import (
    MAX_ACTIVE_KEYS_PER_USER,
    MAX_KEY_DAYS,
    AuthUser,
    KeyInfo,
    NewKey,
    Role,
    UserAccount,
    digests_match,
    key_digest,
    new_key,
    public_id_of,
    validated_display_name,
    validated_email,
    validated_username,
)
from app.domain.credentials import hash_password, new_temporary_password
from app.domain.errors import (
    AccessKeyNotFoundError,
    AccessRuleError,
    AuthenticationRequiredError,
    ForbiddenError,
    InvalidRequestError,
    TooManyAttemptsError,
    UserNotFoundError,
)

LOGIN_OK = "auth.login"
LOGIN_FAILED = "auth.login_failed"
USER_CREATED = "user.created"
USER_UPDATED = "user.updated"
KEY_CREATED = "access_key.created"
KEY_REVOKED = "access_key.revoked"
# ADR-0047: ver la llave de API de alguien y prender o apagar el código.
KEY_REVEALED = "access_key.revealed"
TOTP_SETTING = "auth.totp_setting"
# Etiqueta de la llave de API de cada persona (la que se puede volver a ver).
API_KEY_LABEL = "Llave de API"
USER_DELETED = "user.deleted"
PASSWORD_RESET = "user.password_reset"  # noqa: S105 — nombre de acción de la bitácora, no una contraseña
TOTP_RESET = "user.totp_reset"

_BAD_KEY = "La llave no es válida, está vencida o fue revocada."
_NO_SESSION = "Tu sesión terminó. Vuelve a entrar con tu usuario y contraseña."
_TOO_MANY = "Demasiados intentos fallidos desde este equipo. Espera unos minutos."
# Huella de relleno: si la parte pública no existe, igual se calcula una
# huella y se compara, para que tarde lo mismo que con una llave real.
_DUMMY_DIGEST = "0" * 64
# Para qué es una llave («laptop de la oficina»): corto, para la tabla.
MAX_LABEL_CHARS = 80


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """Tiempos de la sesión (vienen de la configuración).

    Attributes:
        max_seconds: Duración máxima desde que se entra.
        idle_seconds: Se cierra tras este tiempo sin uso.
        recheck_seconds: Cada cuánto se revisa la llave en la base.
    """

    max_seconds: int
    idle_seconds: int
    recheck_seconds: int


@dataclass(frozen=True, slots=True)
class OpenedSession:
    """Resultado de entrar.

    Attributes:
        token: Valor de la cookie (no se guarda tal cual en Redis).
        user: La persona.
        max_seconds: Vida máxima de la cookie.
    """

    token: str
    user: AuthUser
    max_seconds: int


def require_superuser(user: AuthUser) -> None:
    """Corta si la persona no es superusuario.

    Raises:
        ForbiddenError: Si es un usuario normal.
    """
    if not user.is_superuser:
        raise ForbiddenError("Esta sección es solo para superusuarios.")


class Authenticator:
    """Entrar, reconocer a la persona en cada petición y salir."""

    def __init__(  # noqa: PLR0913 — cada colaborador por nombre (*), sin agruparlos a la fuerza
        self,
        *,
        store: AccessStorePort,
        sessions: SessionStorePort,
        limiter: LoginLimiterPort,
        pepper: bytes,
        policy: SessionPolicy,
        clock: Callable[[], datetime],
    ) -> None:
        """Recibe sus colaboradores.

        Args:
            store: Personas y llaves.
            sessions: Sesiones abiertas.
            limiter: Freno de intentos.
            pepper: Secreto del servidor para las huellas.
            policy: Tiempos de la sesión.
            clock: Hora actual (UTC).
        """
        self._store = store
        self._sessions = sessions
        self._limiter = limiter
        self._pepper = pepper
        self._policy = policy
        self._clock = clock

    async def _verify(self, key: str, ip: str | None) -> tuple[AuthUser, int]:
        if await self._limiter.blocked(ip):
            raise TooManyAttemptsError(_TOO_MANY)
        public_id = public_id_of(key)
        record = await self._store.find_key(public_id) if public_id else None
        candidate = key_digest(key, self._pepper)
        matches = digests_match(record.key_hash if record else _DUMMY_DIGEST, candidate)
        if record is None or not matches or not record.usable(self._clock()):
            await self._limiter.failure(ip)
            await self._store.record_event(
                AuditEntry(
                    Actor(record.user.username if record and matches else "anonimo", ip),
                    LOGIN_FAILED,
                    {"llave": f"{public_id}…" if public_id else "mal formada"},
                ),
                str(record.key_id) if record else "",
            )
            raise AuthenticationRequiredError(_BAD_KEY)
        await self._limiter.clear(ip)
        await self._store.mark_key_used(record.key_id, ip)
        return record.user, record.key_id

    async def from_bearer(self, key: str, ip: str | None) -> AuthUser:
        """La persona de una llave mandada en ``Authorization: Bearer`` (integraciones).

        Raises:
            TooManyAttemptsError: Si esa IP ya falló demasiadas veces.
            AuthenticationRequiredError: Si la llave no sirve.
        """
        user, _ = await self._verify(key, ip)
        return user

    async def from_session(self, token: str) -> AuthUser:
        """La persona de una sesión abierta.

        Raises:
            AuthenticationRequiredError: Si la sesión no existe, pasó su tope o
                su llave ya no sirve.
        """
        data = await self._sessions.get(token, self._policy.idle_seconds)
        if data is None:
            raise AuthenticationRequiredError(_NO_SESSION)
        now = self._clock()
        if now - data.created_at > timedelta(seconds=self._policy.max_seconds):
            await self._sessions.delete(token)
            raise AuthenticationRequiredError(_NO_SESSION)
        if now - data.checked_at >= timedelta(seconds=self._policy.recheck_seconds):
            current = await self._current_user(data, now)
            if current is None:
                await self._sessions.delete(token)
                raise AuthenticationRequiredError(_NO_SESSION)
            data = replace(data, user=current, checked_at=now)
            await self._sessions.save(token, data, self._policy.idle_seconds)
        return data.user

    async def _current_user(self, data: SessionData, now: datetime) -> AuthUser | None:
        # Sesión de contraseña: la persona debe seguir activa. Sesión de llave:
        # la llave debe seguir vigente.
        if data.key_id is None:
            creds = await self._store.credentials(data.user.user_id)
            return creds.user if creds is not None and creds.is_active else None
        record = await self._store.key_record(data.key_id)
        return record.user if record is not None and record.usable(now) else None

    async def introspect(self, token: str) -> AuthUser | None:
        """De quién es un token interno (para otros módulos de Oráculo).

        Args:
            token: El valor de la cookie ``monitor_sesion`` que le llegó al módulo.

        Returns:
            La persona, o ``None`` si el token no existe, venció o ya no sirve.
        """
        try:
            return await self.from_session(token)
        except AuthenticationRequiredError:
            return None

    async def logout(self, token: str) -> None:
        """Cierra la sesión (si no existía, no pasa nada)."""
        await self._sessions.delete(token)


@dataclass(frozen=True, slots=True)
class IssuedKey:
    """Una llave recién creada.

    Attributes:
        key: El texto completo (mostrar una sola vez).
        info: Sus datos guardados.
    """

    key: NewKey
    info: KeyInfo


@dataclass(frozen=True, slots=True)
class CreatedUser:
    """Una persona recién dada de alta.

    Attributes:
        account: Sus datos.
        temporary_password: Su contraseña temporal; se muestra una sola vez y
            la debe cambiar al primer ingreso.
    """

    account: UserAccount
    temporary_password: str


class AccessAdmin:
    """Administración de personas y llaves (solo superusuarios)."""

    def __init__(  # noqa: PLR0913 — cada colaborador por nombre
        self,
        store: AccessStorePort,
        sessions: SessionStorePort,
        pepper: bytes,
        clock: Callable[[], datetime],
        on_user_created: Callable[[str], Awaitable[object]] | None = None,
        *,
        box: SecretBoxPort | None = None,
    ) -> None:
        """Recibe sus colaboradores.

        Args:
            store: Personas y llaves.
            sessions: Para cerrar sesiones al revocar o desactivar.
            pepper: Secreto del servidor para las huellas.
            clock: Hora actual (UTC).
            on_user_created: Qué más darle a una persona nueva (su envío
                inicial de la FGR, ADR-0046); recibe su ``username``.
            box: Cifra la llave de API de cada persona para poder volver a
                mostrarla (ADR-0047). Sin ella, no hay llaves visibles.
        """
        self._store = store
        self._sessions = sessions
        self._pepper = pepper
        self._clock = clock
        self._on_user_created = on_user_created
        self._box = box

    async def list_users(self, admin: AuthUser) -> list[UserAccount]:
        """Todas las personas.

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
        """
        require_superuser(admin)
        return await self._store.list_users()

    async def create_user(  # noqa: PLR0913 — los campos de la persona, por nombre (*)
        self,
        admin: AuthUser,
        ip: str | None,
        *,
        username: str,
        display_name: str,
        email: str | None,
        role: Role,
    ) -> CreatedUser:
        """Da de alta a una persona con una contraseña temporal.

        Al primer ingreso, la persona cambia la contraseña por una suya y da
        de alta su Microsoft Authenticator (ADR-0043).

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            InvalidRequestError: Si un dato no es válido.
            UsernameTakenError: Si el usuario ya existe.
        """
        require_superuser(admin)
        user = NewUser(
            validated_username(username),
            validated_display_name(display_name),
            validated_email(email),
            role,
        )
        actor = Actor(admin.username, ip)
        account = await self._store.create_user(
            user,
            AuditEntry(
                actor,
                USER_CREATED,
                {"username": user.username, "role": user.role.value, "email": user.email},
            ),
        )
        temporary = new_temporary_password()
        await self._store.set_password(
            account.user_id,
            hash_password(temporary),
            True,
            AuditEntry(actor, PASSWORD_RESET, {"username": user.username}),
        )
        if self._on_user_created is not None:
            await self._on_user_created(user.username)
        # Cada persona nace con su llave de API (ADR-0047).
        if self._box is not None:
            await self._new_api_key(admin, ip, account)
        refreshed = await self._store.get_user(account.user_id)
        return CreatedUser(refreshed or account, temporary)

    async def reset_password(self, admin: AuthUser, ip: str | None, user_id: int) -> str:
        """Le da a una persona una contraseña temporal nueva (la olvidó).

        Cierra sus sesiones y la persona la cambia al entrar. Su
        Authenticator se queda como estaba.

        Returns:
            La contraseña temporal (se muestra una sola vez).

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            UserNotFoundError: Si no existe.
        """
        require_superuser(admin)
        account = await self._store.get_user(user_id)
        if account is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        temporary = new_temporary_password()
        await self._store.set_password(
            user_id,
            hash_password(temporary),
            True,
            AuditEntry(Actor(admin.username, ip), PASSWORD_RESET, {"username": account.username}),
        )
        await self._sessions.delete_for_user(user_id)
        return temporary

    async def reset_totp(self, admin: AuthUser, ip: str | None, user_id: int) -> None:
        """Borra el Authenticator de una persona (perdió o cambió de celular).

        Cierra sus sesiones; al volver a entrar escanea un QR nuevo.

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            UserNotFoundError: Si no existe.
        """
        require_superuser(admin)
        account = await self._store.get_user(user_id)
        if account is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        await self._store.set_totp(
            user_id,
            None,
            AuditEntry(Actor(admin.username, ip), TOTP_RESET, {"username": account.username}),
        )
        await self._sessions.delete_for_user(user_id)

    async def update_user(
        self, admin: AuthUser, ip: str | None, user_id: int, changes: UserChanges
    ) -> UserAccount:
        """Cambia nombre, correo, rol o si está activa.

        Desactivar a alguien o cambiarle el rol cierra sus sesiones.

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            UserNotFoundError: Si no existe.
            AccessRuleError: Si se quitaría el rol o se desactivaría a sí mismo,
                o al último superusuario activo.
        """
        require_superuser(admin)
        current = await self._store.get_user(user_id)
        if current is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        clean = UserChanges(
            display_name=(
                validated_display_name(changes.display_name)
                if changes.display_name is not None
                else None
            ),
            email=(validated_email(changes.email) or "") if changes.email is not None else None,
            role=changes.role,
            is_active=changes.is_active,
        )
        loses_admin = (
            current.role is Role.SUPERUSER
            and current.is_active
            and (
                (clean.role is not None and clean.role is not Role.SUPERUSER)
                or clean.is_active is False
            )
        )
        if loses_admin and current.user_id == admin.user_id:
            raise AccessRuleError("No puedes quitarte tu propio rol ni desactivarte.")
        if loses_admin and await self._store.active_superusers() <= 1:
            raise AccessRuleError("Debe quedar al menos un superusuario activo.")
        updated = await self._store.update_user(
            user_id,
            clean,
            AuditEntry(
                Actor(admin.username, ip),
                USER_UPDATED,
                {
                    "before": _account_snapshot(current),
                    "changes": {
                        k: (v.value if isinstance(v, Role) else v)
                        for k, v in (
                            ("display_name", clean.display_name),
                            ("email", clean.email),
                            ("role", clean.role),
                            ("is_active", clean.is_active),
                        )
                        if v is not None
                    },
                },
            ),
        )
        if updated is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        if updated.role is not current.role or not updated.is_active:
            await self._sessions.delete_for_user(user_id)
        return updated

    async def delete_user(self, admin: AuthUser, ip: str | None, user_id: int) -> None:
        """Borra a una persona (borrado lógico) y cierra sus sesiones.

        Desaparece de «Accesos» y ya no puede entrar: se le quitan contraseña,
        código y llaves, y se apagan sus envíos programados (no se borran).
        Sus búsquedas y casos se quedan (los ven los
        superusuarios) y su usuario queda reservado para que nadie nuevo los
        herede. La bitácora conserva todo.

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            UserNotFoundError: Si no existe o ya estaba borrada.
            AccessRuleError: Si es uno mismo o el último superusuario activo.
        """
        require_superuser(admin)
        account = await self._store.get_user(user_id)
        if account is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        if account.user_id == admin.user_id:
            raise AccessRuleError("No puedes borrarte a ti mismo.")
        last_admin = account.role is Role.SUPERUSER and account.is_active
        if last_admin and await self._store.active_superusers() <= 1:
            raise AccessRuleError("Debe quedar al menos un superusuario activo.")
        deleted = await self._store.delete_user(
            user_id,
            AuditEntry(
                Actor(admin.username, ip), USER_DELETED, {"before": _account_snapshot(account)}
            ),
        )
        if not deleted:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        await self._sessions.delete_for_user(user_id)

    async def user_keys(self, admin: AuthUser, user_id: int) -> list[KeyInfo]:
        """Las llaves de una persona (sin secretos).

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            UserNotFoundError: Si no existe.
        """
        require_superuser(admin)
        if await self._store.get_user(user_id) is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        return await self._store.user_keys(user_id)

    async def issue_key(
        self,
        admin: AuthUser,
        ip: str | None,
        user_id: int,
        label: str,
        days: int | None,
    ) -> IssuedKey:
        """Crea una llave para una persona. El texto completo solo sale aquí.

        Args:
            admin: Quién la crea.
            ip: Desde dónde.
            user_id: Para quién.
            label: Para qué es (hasta 80 caracteres).
            days: Días de vigencia (1 a 365) o ``None`` para que no venza.

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            UserNotFoundError: Si no existe la persona.
            InvalidRequestError: Si la vigencia o la etiqueta no son válidas.
            AccessRuleError: Si la persona está desactivada o ya tiene el tope
                de llaves vigentes.
        """
        require_superuser(admin)
        user = await self._store.get_user(user_id)
        if user is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        if not user.is_active:
            raise AccessRuleError("Activa a la persona antes de darle una llave.")
        if user.active_keys >= MAX_ACTIVE_KEYS_PER_USER:
            raise AccessRuleError(
                f"Cada persona puede tener hasta {MAX_ACTIVE_KEYS_PER_USER} llaves vigentes. "
                "Revoca una antes de crear otra."
            )
        clean_label = " ".join(label.split())
        if len(clean_label) > MAX_LABEL_CHARS:
            raise InvalidRequestError(f"La etiqueta admite hasta {MAX_LABEL_CHARS} caracteres.")
        if days is not None and not 1 <= days <= MAX_KEY_DAYS:
            raise InvalidRequestError(f"La vigencia va de 1 a {MAX_KEY_DAYS} días.")
        key = new_key()
        expires_at = self._clock() + timedelta(days=days) if days is not None else None
        info = await self._store.create_key(
            NewKeyRow(
                user_id, key.public_id, key_digest(key.full, self._pepper), clean_label, expires_at
            ),
            AuditEntry(
                Actor(admin.username, ip),
                KEY_CREATED,
                {"para": user.username, "llave": key.masked, "dias": days, "etiqueta": clean_label},
            ),
        )
        return IssuedKey(key, info)

    async def show_api_key(self, admin: AuthUser, ip: str | None, user_id: int) -> IssuedKey:
        """La llave de API de una persona, completa, para verla o copiarla (ADR-0047).

        Cada vez queda en la bitácora (``key.revealed``).

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            UserNotFoundError: Si no existe la persona.
            AccessKeyNotFoundError: Si todavía no tiene una llave visible.
        """
        require_superuser(admin)
        user = await self._store.get_user(user_id)
        if user is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        found = await self._store.api_key(user_id) if self._box else None
        if found is None:
            raise AccessKeyNotFoundError(
                "Esta persona todavía no tiene llave de API: genera una.", {"id": user_id}
            )
        info, sealed = found
        full = self._box.open(sealed) if self._box else ""
        await self._store.record_event(
            AuditEntry(
                Actor(admin.username, ip),
                KEY_REVEALED,
                {"de": user.username, "llave": info.masked},
            ),
            str(info.key_id),
        )
        return IssuedKey(NewKey(full, info.public_id), info)

    async def new_api_key(self, admin: AuthUser, ip: str | None, user_id: int) -> IssuedKey:
        """Genera la llave de API de una persona; la anterior deja de servir (ADR-0047).

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            UserNotFoundError: Si no existe la persona.
            AccessRuleError: Si la persona está desactivada o el servidor no
                puede cifrar llaves.
        """
        require_superuser(admin)
        user = await self._store.get_user(user_id)
        if user is None:
            raise UserNotFoundError("No existe esa persona.", {"id": user_id})
        if not user.is_active:
            raise AccessRuleError("Activa a la persona antes de darle una llave.")
        return await self._new_api_key(admin, ip, user)

    async def _new_api_key(self, admin: AuthUser, ip: str | None, user: UserAccount) -> IssuedKey:
        if self._box is None:
            raise AccessRuleError(
                "El servidor no puede guardar llaves visibles (falta la pimienta)."
            )
        actor = Actor(admin.username, ip)
        # La anterior se revoca: una sola llave de API por persona.
        for old in await self._store.user_keys(user.user_id):
            if old.revealable and old.revoked_at is None:
                await self._store.revoke_key(
                    old.key_id, AuditEntry(actor, KEY_REVOKED, {"llave_id": old.key_id})
                )
                await self._sessions.delete_for_user(user.user_id, old.key_id)
        key = new_key()
        info = await self._store.create_key(
            NewKeyRow(
                user.user_id,
                key.public_id,
                key_digest(key.full, self._pepper),
                API_KEY_LABEL,
                None,
                self._box.seal(key.full),
            ),
            AuditEntry(
                actor,
                KEY_CREATED,
                {
                    "para": user.username,
                    "llave": key.masked,
                    "dias": None,
                    "etiqueta": API_KEY_LABEL,
                },
            ),
        )
        return IssuedKey(key, info)

    async def totp_required(self, admin: AuthUser) -> bool:
        """Si al entrar se pide el código de 6 dígitos.

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
        """
        require_superuser(admin)
        return await self._store.totp_required()

    async def set_totp_required(self, admin: AuthUser, ip: str | None, required: bool) -> bool:
        """Prende o apaga el código de 6 dígitos para todos (ADR-0047).

        Aplica en el siguiente ingreso; las sesiones abiertas siguen.

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
        """
        require_superuser(admin)
        await self._store.set_totp_required(
            required,
            AuditEntry(Actor(admin.username, ip), TOTP_SETTING, {"pedir_codigo": required}),
        )
        return required

    async def revoke_key(self, admin: AuthUser, ip: str | None, key_id: int) -> KeyInfo:
        """Revoca una llave y cierra las sesiones de su dueño.

        Raises:
            ForbiddenError: Si quien pide no es superusuario.
            AccessKeyNotFoundError: Si no existe.
            AccessRuleError: Si es la única llave vigente de quien revoca.
        """
        require_superuser(admin)
        now = self._clock()
        own = [k for k in await self._store.user_keys(admin.user_id) if _vigente(k, now)]
        if len(own) == 1 and own[0].key_id == key_id:
            raise AccessRuleError("Es tu única llave vigente: crea otra antes de revocarla.")
        info = await self._store.revoke_key(
            key_id, AuditEntry(Actor(admin.username, ip), KEY_REVOKED, {"llave_id": key_id})
        )
        if info is None:
            raise AccessKeyNotFoundError("No existe esa llave.", {"id": key_id})
        # Solo las sesiones que entraron con esa llave: las demás siguen.
        await self._sessions.delete_for_user(info.user_id, key_id)
        return info


def _vigente(key: KeyInfo, now: datetime) -> bool:
    return key.revoked_at is None and (key.expires_at is None or now < key.expires_at)


def _account_snapshot(user: UserAccount) -> dict[str, object]:
    return {
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
    }
