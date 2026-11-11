"""Entrar al monitor con usuario, contraseña y código de 6 dígitos (ADR-0043).

Igual que en Oráculo, se entra en pasos:

1. **Usuario y contraseña** (``start``). Si están bien, se abre un «ingreso a
   medias» (``LoginTicket``) que vive 10 minutos y dice qué falta.
2. **Primer ingreso:** si la contraseña es temporal, se cambia
   (``change_password``); si todavía no hay Microsoft Authenticator, se da de
   alta escaneando un QR (``start_enrollment`` y ``confirm_enrollment``).
3. **Código de 6 dígitos** (``verify_code``). Con eso se abre la sesión: el
   **token interno** que identifica a la persona en cada petición y que, más
   adelante, los demás módulos de Oráculo podrán consultar (``introspect``).

Reglas de seguridad:

- el mismo mensaje si el usuario no existe, la contraseña está mal o la
  cuenta está bloqueada o desactivada (no se da pista de qué usuarios hay), y
  se calcula scrypt aunque el usuario no exista, para tardar lo mismo;
- 5 fallos seguidos bloquean la cuenta 15 minutos, y 10 fallos por IP en
  15 minutos bloquean esa IP;
- un ingreso a medias admite 5 códigos equivocados y luego hay que empezar
  de nuevo; un código ya usado no vuelve a servir.

No hace: no sabe de cookies ni de HTTP, ni dibuja el QR por sí mismo.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal, NoReturn

from app.application.audit import Actor, AuditEntry
from app.application.ports.access import (
    AccessStorePort,
    LoginLimiterPort,
    LoginTicket,
    LoginTicketStorePort,
    QrRendererPort,
    SecretBoxPort,
    SessionData,
    SessionStorePort,
    UserCredentials,
)
from app.application.use_cases.access import OpenedSession, SessionPolicy
from app.domain.access import AuthUser
from app.domain.credentials import (
    MAX_USER_FAILURES,
    USER_LOCK_MINUTES,
    hash_password,
    matching_totp_counter,
    new_totp_secret,
    totp_enrollment,
    validated_password,
    verify_password,
)
from app.domain.errors import (
    AuthenticationRequiredError,
    InvalidRequestError,
    TooManyAttemptsError,
)

LOGIN_OK = "auth.login"
LOGIN_FAILED = "auth.login_failed"
PASSWORD_CHANGED = "user.password_changed"  # noqa: S105 — nombre de acción de la bitácora, no una contraseña
TOTP_ENROLLED = "user.totp_enrolled"

# Un ingreso a medias vive 10 minutos: tiempo de sobra para abrir la app del
# celular o escanear el QR, sin dejar la puerta entreabierta mucho rato.
TICKET_SECONDS = 600
# Códigos equivocados por ingreso antes de pedir la contraseña otra vez.
MAX_CODE_ATTEMPTS = 5

_BAD_LOGIN = "Usuario o contraseña incorrectos, o la cuenta está bloqueada por intentos."
_BAD_CODE = "El código no es correcto o ya se usó. Espera el siguiente y vuelve a intentar."
_EXPIRED = "El ingreso venció o ya no es válido. Vuelve a escribir tu usuario y contraseña."
_TOO_MANY = "Demasiados intentos fallidos desde este equipo. Espera unos minutos."

NextStep = Literal["code", "change_password", "enroll"]


@dataclass(frozen=True, slots=True)
class LoginStep:
    """Qué sigue en un ingreso a medias.

    Attributes:
        ticket: Valor que el navegador manda en el siguiente paso.
        next: ``code`` (escribir el código), ``change_password`` (cambiar la
            temporal) o ``enroll`` (dar de alta Microsoft Authenticator).
    """

    ticket: str
    next: NextStep


@dataclass(frozen=True, slots=True)
class Enrollment:
    """Lo que se le muestra para dar de alta su Authenticator.

    Attributes:
        secret: Secreto en base32 (por si no puede escanear).
        uri: ``otpauth://`` del QR.
        qr_svg: El QR como imagen SVG.
    """

    secret: str
    uri: str
    qr_svg: str


def _next_step(ticket: LoginTicket) -> NextStep:
    if ticket.must_change_password:
        return "change_password"
    if ticket.needs_enrollment:
        return "enroll"
    return "code"


class PasswordLogin:
    """El paso a paso de entrar con contraseña y código."""

    def __init__(  # noqa: PLR0913 — cada colaborador por nombre (*), sin agruparlos a la fuerza
        self,
        *,
        store: AccessStorePort,
        sessions: SessionStorePort,
        tickets: LoginTicketStorePort,
        limiter: LoginLimiterPort,
        box: SecretBoxPort,
        qr: QrRendererPort,
        policy: SessionPolicy,
        clock: Callable[[], datetime],
    ) -> None:
        """Recibe sus colaboradores.

        Args:
            store: Personas y credenciales.
            sessions: Donde se abre la sesión al final.
            tickets: Ingresos a medias.
            limiter: Freno de intentos por IP.
            box: Cifra el secreto del código.
            qr: Dibuja el QR.
            policy: Tiempos de la sesión.
            clock: Hora actual (UTC).
        """
        self._store = store
        self._sessions = sessions
        self._tickets = tickets
        self._limiter = limiter
        self._box = box
        self._qr = qr
        self._policy = policy
        self._clock = clock

    async def _fail(self, ip: str | None, who: str, reason: str) -> None:
        await self._limiter.failure(ip)
        await self._store.record_event(
            AuditEntry(Actor(who, ip), LOGIN_FAILED, {"motivo": reason}), ""
        )

    async def start(self, username: str, password: str, ip: str | None) -> LoginStep:
        """Paso 1: usuario y contraseña.

        Args:
            username: Usuario (no distingue mayúsculas).
            password: Contraseña.
            ip: Desde dónde.

        Returns:
            El ingreso a medias y qué sigue.

        Raises:
            TooManyAttemptsError: Si esa IP ya falló demasiadas veces.
            AuthenticationRequiredError: Si algo no cuadra (mismo mensaje
                siempre).
        """
        if await self._limiter.blocked(ip):
            raise TooManyAttemptsError(_TOO_MANY)
        now = self._clock()
        creds = await self._store.find_credentials(username.strip().lower())
        # Se calcula scrypt siempre (con huella de relleno si no hay usuario).
        matches = verify_password(password, creds.password_hash if creds else None)
        locked = creds is not None and creds.locked_until is not None and now < creds.locked_until
        if creds is None or not creds.is_active or locked or not matches:
            if creds is not None and not locked and not matches:
                # Si ya pasó un bloqueo anterior, se cuenta desde cero otra vez.
                expired_lock = creds.locked_until is not None and now >= creds.locked_until
                failures = (0 if expired_lock else creds.failed_logins) + 1
                lock_until = (
                    now + timedelta(minutes=USER_LOCK_MINUTES)
                    if failures >= MAX_USER_FAILURES
                    else None
                )
                await self._store.login_failed(creds.user.user_id, failures, lock_until)
            await self._fail(
                ip,
                creds.user.username if creds else "anonimo",
                "bloqueada" if locked else "contraseña" if creds else "usuario",
            )
            raise AuthenticationRequiredError(_BAD_LOGIN)
        ticket = LoginTicket(
            user_id=creds.user.user_id,
            username=creds.user.username,
            must_change_password=creds.must_change_password,
            needs_enrollment=creds.totp_secret is None,
        )
        token = await self._tickets.create(ticket, TICKET_SECONDS)
        return LoginStep(token, _next_step(ticket))

    async def _ticket(self, token: str) -> LoginTicket:
        ticket = await self._tickets.get(token)
        if ticket is None:
            raise AuthenticationRequiredError(_EXPIRED)
        return ticket

    async def change_password(self, token: str, new_password: str, ip: str | None) -> LoginStep:
        """Primer ingreso: cambia la contraseña temporal por una propia.

        Raises:
            AuthenticationRequiredError: Si el ingreso venció.
            InvalidRequestError: Si la contraseña nueva no cumple las reglas o
                es igual a la temporal.
        """
        ticket = await self._ticket(token)
        if not ticket.must_change_password:
            return LoginStep(token, _next_step(ticket))
        validated_password(new_password, ticket.username)
        creds = await self._store.credentials(ticket.user_id)
        if creds is None:
            raise AuthenticationRequiredError(_EXPIRED)
        if verify_password(new_password, creds.password_hash):
            raise InvalidRequestError(
                "La contraseña nueva debe ser distinta a la temporal.",
                {"problemas": [{"campo": "new_password", "mensaje": "Igual a la temporal."}]},
            )
        await self._store.set_password(
            ticket.user_id,
            hash_password(new_password),
            False,
            AuditEntry(Actor(ticket.username, ip), PASSWORD_CHANGED, {}),
        )
        updated = replace(ticket, must_change_password=False)
        await self._tickets.save(token, updated, TICKET_SECONDS)
        return LoginStep(token, _next_step(updated))

    async def start_enrollment(self, token: str) -> Enrollment:
        """Primer ingreso: genera el QR para Microsoft Authenticator.

        Raises:
            AuthenticationRequiredError: Si el ingreso venció o ya tiene
                Authenticator, o si todavía debe cambiar su contraseña.
        """
        ticket = await self._ticket(token)
        if ticket.must_change_password or not ticket.needs_enrollment:
            raise AuthenticationRequiredError(_EXPIRED)
        secret = new_totp_secret()
        await self._tickets.save(
            token, replace(ticket, pending_secret=self._box.seal(secret)), TICKET_SECONDS
        )
        enrollment = totp_enrollment(secret, ticket.username)
        return Enrollment(enrollment.secret, enrollment.uri, self._qr.svg(enrollment.uri))

    async def confirm_enrollment(self, token: str, code: str, ip: str | None) -> OpenedSession:
        """Primer ingreso: el primer código confirma que el celular quedó bien.

        Raises:
            AuthenticationRequiredError: Si el ingreso venció, no se pidió el QR
                o el código no es correcto (tras 5 errores se cancela).
        """
        ticket = await self._ticket(token)
        if ticket.pending_secret is None or ticket.must_change_password:
            raise AuthenticationRequiredError(_EXPIRED)
        secret = self._box.open(ticket.pending_secret)
        counter = matching_totp_counter(secret, code, self._clock(), None)
        if counter is None:
            await self._wrong_code(token, ticket, ip)
        await self._store.set_totp(
            ticket.user_id,
            ticket.pending_secret,
            AuditEntry(Actor(ticket.username, ip), TOTP_ENROLLED, {}),
        )
        await self._store.use_totp_counter(ticket.user_id, counter)
        return await self._open(token, ticket, ip)

    async def verify_code(self, token: str, code: str, ip: str | None) -> OpenedSession:
        """Paso final: el código de 6 dígitos abre la sesión.

        Raises:
            TooManyAttemptsError: Si esa IP ya falló demasiadas veces.
            AuthenticationRequiredError: Si el ingreso venció, falta un paso o
                el código no es correcto (tras 5 errores se cancela).
        """
        if await self._limiter.blocked(ip):
            raise TooManyAttemptsError(_TOO_MANY)
        ticket = await self._ticket(token)
        if ticket.must_change_password or ticket.needs_enrollment:
            raise AuthenticationRequiredError(_EXPIRED)
        creds = await self._store.credentials(ticket.user_id)
        if creds is None or not creds.is_active or creds.totp_secret is None:
            await self._tickets.delete(token)
            raise AuthenticationRequiredError(_EXPIRED)
        counter = matching_totp_counter(
            self._box.open(creds.totp_secret), code, self._clock(), creds.totp_last_counter
        )
        # use_totp_counter es atómico: si dos peticiones traen el mismo código
        # a la vez, solo una gana.
        if counter is None or not await self._store.use_totp_counter(ticket.user_id, counter):
            await self._wrong_code(token, ticket, ip)
        return await self._open(token, ticket, ip, creds)

    async def _wrong_code(self, token: str, ticket: LoginTicket, ip: str | None) -> NoReturn:
        await self._fail(ip, ticket.username, "código")
        attempts = ticket.attempts + 1
        if attempts >= MAX_CODE_ATTEMPTS:
            await self._tickets.delete(token)
            raise AuthenticationRequiredError(_EXPIRED)
        await self._tickets.save(token, replace(ticket, attempts=attempts), TICKET_SECONDS)
        raise AuthenticationRequiredError(_BAD_CODE)

    async def _open(
        self,
        token: str,
        ticket: LoginTicket,
        ip: str | None,
        creds: UserCredentials | None = None,
    ) -> OpenedSession:
        creds = creds or await self._store.credentials(ticket.user_id)
        if creds is None:
            raise AuthenticationRequiredError(_EXPIRED)
        await self._tickets.delete(token)
        await self._limiter.clear(ip)
        await self._store.login_succeeded(ticket.user_id, ip)
        now = self._clock()
        user: AuthUser = creds.user
        session = await self._sessions.create(
            SessionData(user, None, now, now),
            self._policy.idle_seconds,
            self._policy.max_seconds,
        )
        await self._store.record_event(
            AuditEntry(Actor(user.username, ip), LOGIN_OK, {"metodo": "contraseña+código"}),
            str(user.user_id),
        )
        return OpenedSession(session, user, self._policy.max_seconds)

    async def change_own_password(
        self, user: AuthUser, current: str, new_password: str, ip: str | None
    ) -> OpenedSession:
        """«Cambiar mi contraseña» con la sesión abierta.

        Cierra todas las sesiones de la persona (si alguien más tenía una
        abierta, queda fuera) y abre una nueva para el navegador que la cambió.

        Returns:
            La sesión nueva (la API pone su cookie).

        Raises:
            InvalidRequestError: Si la contraseña actual no es correcta (no es
                401: escribirla mal no debe sacar a nadie de su sesión) o la
                nueva no cumple las reglas.
        """
        creds = await self._store.credentials(user.user_id)
        if creds is None or not verify_password(current, creds.password_hash):
            await self._fail(ip, user.username, "contraseña actual")
            raise InvalidRequestError(
                "Tu contraseña actual no es correcta.",
                {"problemas": [{"campo": "current_password", "mensaje": "No es correcta."}]},
            )
        validated_password(new_password, user.username)
        await self._store.set_password(
            user.user_id,
            hash_password(new_password),
            False,
            AuditEntry(Actor(user.username, ip), PASSWORD_CHANGED, {}),
        )
        await self._sessions.delete_for_user(user.user_id)
        now = self._clock()
        session = await self._sessions.create(
            SessionData(creds.user, None, now, now),
            self._policy.idle_seconds,
            self._policy.max_seconds,
        )
        return OpenedSession(session, creds.user, self._policy.max_seconds)
