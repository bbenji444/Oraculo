"""Personas, credenciales, llaves, sesiones e ingresos en memoria (pruebas sin base)."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from app.application.audit import AuditEntry
from app.application.ports.access import (
    LoginTicket,
    NewKeyRow,
    NewUser,
    SessionData,
    UserChanges,
    UserCredentials,
)
from app.application.use_cases.access import AccessAdmin, Authenticator, SessionPolicy
from app.application.use_cases.login import PasswordLogin
from app.domain.access import AuthUser, KeyInfo, KeyRecord, Role, UserAccount
from app.domain.errors import UsernameTakenError

PEPPER = b"pimienta-de-prueba-con-mas-de-32-caracteres"
T0 = datetime(2026, 11, 10, 18, tzinfo=UTC)
# Igual que el servidor: hasta 30 días sin cierre por inactividad (ADR-0043).
THIRTY_DAYS = 30 * 24 * 3600
POLICY = SessionPolicy(max_seconds=THIRTY_DAYS, idle_seconds=THIRTY_DAYS, recheck_seconds=300)


class Clock:
    """Reloj que avanza a mano."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@dataclass
class _Key:
    info: KeyInfo
    key_hash: str


@dataclass
class _Creds:
    password_hash: str | None = None
    must_change: bool = True
    totp_secret: str | None = None
    last_counter: int | None = None
    failed: int = 0
    locked_until: datetime | None = None


@dataclass
class FakeAccessStore:
    """``AccessStorePort`` en memoria."""

    clock: Clock
    users: dict[int, UserAccount] = field(default_factory=dict)
    keys: dict[int, _Key] = field(default_factory=dict)
    events: list[tuple[AuditEntry, str]] = field(default_factory=list)
    used: list[tuple[int, str | None]] = field(default_factory=list)
    creds: dict[int, _Creds] = field(default_factory=dict)

    def add_user(self, username: str, role: Role = Role.USER, *, active: bool = True) -> int:
        user_id = len(self.users) + 1
        self.users[user_id] = UserAccount(
            user_id, username, username.capitalize(), None, role, active, T0, None
        )
        self.creds[user_id] = _Creds()
        return user_id

    def _credentials(self, user_id: int) -> UserCredentials:
        user = self.users[user_id]
        c = self.creds[user_id]
        return UserCredentials(
            AuthUser(user.user_id, user.username, user.display_name, user.role),
            user.is_active,
            c.password_hash,
            c.must_change,
            c.totp_secret,
            c.last_counter,
            c.failed,
            c.locked_until,
        )

    async def find_credentials(self, username: str) -> UserCredentials | None:
        found = next((u for u in self.users.values() if u.username == username), None)
        return self._credentials(found.user_id) if found else None

    async def credentials(self, user_id: int) -> UserCredentials | None:
        return self._credentials(user_id) if user_id in self.users else None

    async def login_failed(
        self, user_id: int, failures: int, locked_until: datetime | None
    ) -> None:
        c = self.creds[user_id]
        c.failed, c.locked_until = failures, locked_until

    async def login_succeeded(self, user_id: int, ip: str | None) -> None:
        c = self.creds[user_id]
        c.failed, c.locked_until = 0, None
        self.users[user_id] = replace(self.users[user_id], last_seen_at=self.clock())

    async def set_password(
        self, user_id: int, password_hash: str, must_change: bool, audit: AuditEntry
    ) -> None:
        c = self.creds[user_id]
        c.password_hash, c.must_change, c.failed, c.locked_until = (
            password_hash,
            must_change,
            0,
            None,
        )
        self.events.append((audit, str(user_id)))

    async def set_totp(self, user_id: int, secret: str | None, audit: AuditEntry) -> None:
        c = self.creds[user_id]
        c.totp_secret, c.last_counter = secret, None
        self.events.append((audit, str(user_id)))

    async def use_totp_counter(self, user_id: int, counter: int) -> bool:
        c = self.creds[user_id]
        if c.last_counter is not None and counter <= c.last_counter:
            return False
        c.last_counter = counter
        return True

    def _account(self, user_id: int) -> UserAccount:
        now = self.clock()
        active = sum(
            1
            for k in self.keys.values()
            if k.info.user_id == user_id
            and k.info.revoked_at is None
            and (k.info.expires_at is None or k.info.expires_at > now)
        )
        c = self.creds[user_id]
        return replace(
            self.users[user_id],
            active_keys=active,
            has_password=c.password_hash is not None,
            must_change_password=c.must_change,
            totp_enrolled=c.totp_secret is not None,
            locked_until=c.locked_until,
        )

    def _record(self, key: _Key) -> KeyRecord:
        user = self.users[key.info.user_id]
        return KeyRecord(
            key.info.key_id,
            key.key_hash,
            AuthUser(user.user_id, user.username, user.display_name, user.role),
            user.is_active,
            key.info.expires_at,
            key.info.revoked_at,
        )

    async def find_key(self, public_id: str) -> KeyRecord | None:
        key = next((k for k in self.keys.values() if k.info.public_id == public_id), None)
        return self._record(key) if key else None

    async def key_record(self, key_id: int) -> KeyRecord | None:
        key = self.keys.get(key_id)
        return self._record(key) if key else None

    async def mark_key_used(self, key_id: int, ip: str | None) -> None:
        self.used.append((key_id, ip))

    async def record_event(self, audit: AuditEntry, entity_id: str) -> None:
        self.events.append((audit, entity_id))

    async def list_users(self) -> list[UserAccount]:
        return [self._account(i) for i in self.users]

    async def get_user(self, user_id: int) -> UserAccount | None:
        return self._account(user_id) if user_id in self.users else None

    async def active_superusers(self) -> int:
        return sum(1 for u in self.users.values() if u.role is Role.SUPERUSER and u.is_active)

    async def create_user(self, user: NewUser, audit: AuditEntry) -> UserAccount:
        if any(u.username == user.username for u in self.users.values()):
            raise UsernameTakenError("Ya existe.")
        user_id = self.add_user(user.username, user.role)
        self.users[user_id] = replace(
            self.users[user_id], display_name=user.display_name, email=user.email
        )
        self.events.append((audit, str(user_id)))
        return self._account(user_id)

    async def update_user(
        self, user_id: int, changes: UserChanges, audit: AuditEntry
    ) -> UserAccount | None:
        if user_id not in self.users:
            return None
        user = self.users[user_id]
        self.users[user_id] = replace(
            user,
            display_name=changes.display_name or user.display_name,
            email=(changes.email or None) if changes.email is not None else user.email,
            role=changes.role or user.role,
            is_active=user.is_active if changes.is_active is None else changes.is_active,
        )
        self.events.append((audit, str(user_id)))
        return self._account(user_id)

    async def user_keys(self, user_id: int) -> list[KeyInfo]:
        return [k.info for k in self.keys.values() if k.info.user_id == user_id][::-1]

    async def create_key(self, key: NewKeyRow, audit: AuditEntry) -> KeyInfo:
        key_id = len(self.keys) + 1
        info = KeyInfo(
            key_id,
            key.user_id,
            key.public_id,
            key.label,
            audit.actor.user_id,
            self.clock(),
            key.expires_at,
            None,
            None,
            None,
        )
        self.keys[key_id] = _Key(info, key.key_hash)
        self.events.append((audit, str(key_id)))
        return info

    async def revoke_key(self, key_id: int, audit: AuditEntry) -> KeyInfo | None:
        key = self.keys.get(key_id)
        if key is None:
            return None
        key.info = replace(key.info, revoked_at=key.info.revoked_at or self.clock())
        self.events.append((audit, str(key_id)))
        return key.info


class FakeSessions:
    """``SessionStorePort`` en memoria (sin vencimiento por tiempo sin uso)."""

    def __init__(self) -> None:
        self.data: dict[str, SessionData] = {}
        self.counter = 0

    async def create(self, data: SessionData, idle_seconds: int, max_seconds: int) -> str:
        self.counter += 1
        token = f"sesion-{self.counter}"
        self.data[token] = data
        return token

    async def get(self, token: str, idle_seconds: int) -> SessionData | None:
        return self.data.get(token)

    async def save(self, token: str, data: SessionData, idle_seconds: int) -> None:
        self.data[token] = data

    async def delete(self, token: str) -> None:
        self.data.pop(token, None)

    async def delete_for_user(self, user_id: int, key_id: int | None = None) -> int:
        doomed = [
            t
            for t, d in self.data.items()
            if d.user.user_id == user_id and (key_id is None or d.key_id == key_id)
        ]
        for token in doomed:
            del self.data[token]
        return len(doomed)


class FakeTickets:
    """``LoginTicketStorePort`` en memoria (sin vencimiento)."""

    def __init__(self) -> None:
        self.data: dict[str, LoginTicket] = {}
        self.counter = 0

    async def create(self, ticket: LoginTicket, ttl_seconds: int) -> str:
        self.counter += 1
        token = f"ingreso-{self.counter}"
        self.data[token] = ticket
        return token

    async def get(self, token: str) -> LoginTicket | None:
        return self.data.get(token)

    async def save(self, token: str, ticket: LoginTicket, ttl_seconds: int) -> None:
        self.data[token] = ticket

    async def delete(self, token: str) -> None:
        self.data.pop(token, None)


class FakeBox:
    """``SecretBoxPort`` de juguete: marca el texto para ver que no va en claro."""

    def seal(self, plain: str) -> str:
        return "sellado:" + plain[::-1]

    def open(self, sealed: str) -> str:
        if not sealed.startswith("sellado:"):
            msg = "alterado"
            raise ValueError(msg)
        return sealed.removeprefix("sellado:")[::-1]


class FakeQr:
    """``QrRendererPort`` de juguete."""

    def svg(self, content: str) -> str:
        return f"<svg>{content}</svg>"


class FakeLimiter:
    """``LoginLimiterPort`` en memoria."""

    def __init__(self, max_failures: int = 3) -> None:
        self.max = max_failures
        self.failures: dict[str | None, int] = {}

    async def blocked(self, ip: str | None) -> bool:
        return self.failures.get(ip, 0) >= self.max

    async def failure(self, ip: str | None) -> None:
        self.failures[ip] = self.failures.get(ip, 0) + 1

    async def clear(self, ip: str | None) -> None:
        self.failures.pop(ip, None)


@dataclass
class AccessWorld:
    """Todo armado: tienda, sesiones, freno, reloj y casos de uso."""

    clock: Clock
    store: FakeAccessStore
    sessions: FakeSessions
    limiter: FakeLimiter
    auth: Authenticator
    admin: AccessAdmin
    tickets: FakeTickets
    login: PasswordLogin


def access_world() -> AccessWorld:
    """Un mundo nuevo con el superusuario «benji» (id 1)."""
    clock = Clock()
    store = FakeAccessStore(clock)
    store.add_user("benji", Role.SUPERUSER)
    sessions = FakeSessions()
    limiter = FakeLimiter()
    auth = Authenticator(
        store=store,
        sessions=sessions,
        limiter=limiter,
        pepper=PEPPER,
        policy=POLICY,
        clock=clock,
    )
    tickets = FakeTickets()
    login = PasswordLogin(
        store=store,
        sessions=sessions,
        tickets=tickets,
        limiter=limiter,
        box=FakeBox(),
        qr=FakeQr(),
        policy=POLICY,
        clock=clock,
    )
    return AccessWorld(
        clock,
        store,
        sessions,
        limiter,
        auth,
        AccessAdmin(store, sessions, PEPPER, clock),
        tickets,
        login,
    )
