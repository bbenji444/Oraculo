"""Llaves de acceso y roles del monitor (piloto, 10/11/2026, ADR-0042).

El jefe de Benji pidió un «token» como el de la API de ChatGPT o de Claude, con
seguridad altísima. Este módulo tiene las reglas puras:

- **formato:** ``orc_live_<8 públicos>_<40 secretos>``. El prefijo ``orc_`` deja
  que los detectores de secretos reconozcan una llave subida por error; la
  parte pública identifica la llave en pantallas y registros sin revelarla;
- **huella:** la base guarda solo HMAC-SHA256 de la llave con una «pimienta»
  que vive en el ``.env``, fuera de la base. Si roban la tabla, las huellas
  no sirven para entrar;
- **comparación en tiempo constante**, para no dar pistas por lo que tarda;
- **roles:** ``superuser`` (todo, también «Estado del sistema» y «Accesos») y
  ``user`` (Explorar, Casos, Conceptos, Historial y Envíos).

No hace: no guarda nada ni sabe de HTTP (eso es del repositorio y de la API).
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.errors import InvalidRequestError

KEY_PREFIX = "orc_live_"
# Caracteres de la parte pública y del secreto. 40 caracteres de 62 posibles
# son ~238 bits: imposible de adivinar probando (como las llaves de OpenAI).
PUBLIC_CHARS = 8
SECRET_CHARS = 40
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
_KEY = re.compile(
    rf"^{KEY_PREFIX}(?P<public>[A-Za-z0-9]{{{PUBLIC_CHARS}}})_[A-Za-z0-9]{{{SECRET_CHARS}}}$"
)
MAX_USERNAME_CHARS = 60
MAX_DISPLAY_NAME_CHARS = 120
# RFC 5321 limita una dirección a 254 caracteres.
MAX_EMAIL_CHARS = 254
_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Llaves vigentes por persona: una por equipo (oficina, casa, integración)
# alcanza; más llaves sueltas son más superficie de ataque.
MAX_ACTIVE_KEYS_PER_USER = 5
# Vigencia que puede elegir el superusuario al crear una llave (días).
MAX_KEY_DAYS = 365


class Role(StrEnum):
    """Qué puede hacer una persona en el monitor."""

    SUPERUSER = "superuser"
    USER = "user"


@dataclass(frozen=True, slots=True)
class AuthUser:
    """La persona que hace la petición.

    Attributes:
        user_id: Id en ``users``.
        username: Identificador estable («benji»); es el que guardan búsquedas,
            casos y bitácora.
        display_name: Nombre para mostrar.
        role: Su rol.
    """

    user_id: int
    username: str
    display_name: str
    role: Role

    @property
    def is_superuser(self) -> bool:
        """Si puede administrar el sistema."""
        return self.role is Role.SUPERUSER


@dataclass(frozen=True, slots=True)
class NewKey:
    """Una llave recién creada: el texto completo solo existe en este momento.

    Attributes:
        full: La llave completa; se muestra una sola vez y nunca se guarda.
        public_id: Su parte pública (para identificarla sin revelarla).
    """

    full: str
    public_id: str

    @property
    def masked(self) -> str:
        """Cómo se muestra en pantallas y registros: ``orc_live_a1b2c3d4…``."""
        return f"{KEY_PREFIX}{self.public_id}…"


@dataclass(frozen=True, slots=True)
class KeyRecord:
    """Lo que se necesita para decidir si una llave deja entrar.

    Attributes:
        key_id: Id en ``access_keys``.
        key_hash: Huella guardada.
        user: Su dueño.
        user_active: Si la persona sigue activa.
        expires_at: Cuándo vence (``None``: no vence).
        revoked_at: Cuándo se revocó (``None``: vigente).
    """

    key_id: int
    key_hash: str
    user: AuthUser
    user_active: bool
    expires_at: datetime | None
    revoked_at: datetime | None

    def usable(self, now: datetime) -> bool:
        """Si deja entrar ahora: persona activa, sin revocar y sin vencer."""
        if not self.user_active or self.revoked_at is not None:
            return False
        return self.expires_at is None or now < self.expires_at


@dataclass(frozen=True, slots=True)
class UserAccount:
    """Una persona, como la ve la pantalla «Accesos».

    Attributes:
        user_id: Id en ``users``.
        username: Identificador estable.
        display_name: Nombre para mostrar.
        email: Correo (opcional; para los envíos de la etapa 3).
        role: Rol.
        is_active: Si puede entrar.
        created_at: Alta.
        last_seen_at: Última vez que entró.
        active_keys: Llaves vigentes (sin revocar ni vencer).
    """

    user_id: int
    username: str
    display_name: str
    email: str | None
    role: Role
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None
    active_keys: int = 0


@dataclass(frozen=True, slots=True)
class KeyInfo:
    """Una llave, sin su secreto, para la pantalla «Accesos».

    Attributes:
        key_id: Id en ``access_keys``.
        user_id: Dueño.
        public_id: Parte pública (se muestra ``orc_live_<public_id>…``).
        label: Para qué es («laptop de la oficina»).
        created_by: Quién la creó.
        created_at: Cuándo.
        expires_at: Cuándo vence.
        revoked_at: Cuándo se revocó.
        last_used_at: Último uso.
        last_used_ip: Desde dónde.
    """

    key_id: int
    user_id: int
    public_id: str
    label: str
    created_by: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None

    @property
    def masked(self) -> str:
        """``orc_live_a1b2c3d4…``."""
        return f"{KEY_PREFIX}{self.public_id}…"


def validated_display_name(name: str) -> str:
    """Limpia el nombre para mostrar.

    Raises:
        InvalidRequestError: Si queda vacío o pasa de 120 caracteres.
    """
    clean = " ".join(name.split())
    if not clean or len(clean) > MAX_DISPLAY_NAME_CHARS:
        raise InvalidRequestError(
            "El nombre debe tener de 1 a 120 caracteres.",
            {"problemas": [{"campo": "display_name", "mensaje": "Nombre inválido."}]},
        )
    return clean


def validated_email(email: str | None) -> str | None:
    """Revisa la forma del correo (opcional): algo@algo.algo, sin espacios.

    Raises:
        InvalidRequestError: Si no tiene forma de correo.
    """
    if email is None or not email.strip():
        return None
    clean = email.strip().lower()
    if len(clean) > MAX_EMAIL_CHARS or not _EMAIL.match(clean):
        raise InvalidRequestError(
            "El correo no tiene una forma válida.",
            {"problemas": [{"campo": "email", "mensaje": "Correo inválido."}]},
        )
    return clean


def _random(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def new_key() -> NewKey:
    """Genera una llave nueva con el generador criptográfico de Python.

    Returns:
        La llave y su parte pública.

    Example:
        >>> key = new_key()
        >>> key.full.startswith("orc_live_") and len(key.full) == 58
        True
    """
    public = _random(PUBLIC_CHARS)
    return NewKey(f"{KEY_PREFIX}{public}_{_random(SECRET_CHARS)}", public)


def public_id_of(key: str) -> str | None:
    """La parte pública de una llave bien formada, o ``None`` si no tiene la forma.

    Una llave mal formada se rechaza sin consultar la base.

    Example:
        >>> public_id_of("no-es-llave") is None
        True
    """
    match = _KEY.match(key.strip())
    return match.group("public") if match else None


def key_digest(key: str, pepper: bytes) -> str:
    """Huella de una llave: HMAC-SHA256 con la pimienta, en hexadecimal.

    Las llaves son largas y al azar, así que no hace falta un hash lento (como
    bcrypt para contraseñas): la pimienta impide calcular huellas sin el
    servidor.

    Args:
        key: La llave completa.
        pepper: Secreto del servidor (``AUTH_KEY_PEPPER``).

    Returns:
        64 caracteres hexadecimales.
    """
    return hmac.new(pepper, key.strip().encode(), hashlib.sha256).hexdigest()


def digests_match(stored: str, candidate: str) -> bool:
    """Compara dos huellas en tiempo constante."""
    return hmac.compare_digest(stored, candidate)


def session_digest(token: str) -> str:
    """Huella de un identificador de sesión, para no guardar el valor de la cookie."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_session_token() -> str:
    """Identificador de sesión al azar (256 bits), para la cookie."""
    return secrets.token_urlsafe(32)


def validated_username(username: str) -> str:
    """Limpia y valida el identificador de una persona («benji», «ana.lopez»).

    Raises:
        InvalidRequestError: Si queda vacío, es muy largo o lleva caracteres
            que no son letras, números, punto, guion o guion bajo.
    """
    clean = username.strip().lower()
    if not clean or len(clean) > MAX_USERNAME_CHARS or not _USERNAME.match(clean):
        raise InvalidRequestError(
            "El usuario debe tener de 1 a 60 caracteres: letras, números, punto, guion o "
            "guion bajo, sin espacios.",
            {"problemas": [{"campo": "username", "mensaje": "Usuario inválido."}]},
        )
    return clean
