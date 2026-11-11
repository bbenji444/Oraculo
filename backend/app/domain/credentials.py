"""Contraseñas y códigos de 6 dígitos de cada persona (ADR-0043).

Benji pidió entrar al monitor igual que a Oráculo: usuario, contraseña y el
código de 6 dígitos de Microsoft Authenticator. Este módulo tiene las reglas
puras, solo con la biblioteca estándar de Python:

- **contraseñas:** se guarda la huella ``scrypt`` (con sal al azar). scrypt
  es lento a propósito y usa mucha memoria, así que probar millones de
  contraseñas contra una huella robada sale carísimo;
- **códigos de 6 dígitos (TOTP, RFC 6238):** los mismos de Microsoft o Google
  Authenticator: cambian cada 30 s y salen de un secreto que comparten el
  celular y el servidor. Se acepta el código anterior y el siguiente (por si
  el reloj del celular va un poco desfasado) y **nunca el mismo dos veces**;
- **reglas de contraseña:** al menos 12 caracteres, con letras y números, y
  que no contenga el usuario.

No hace: no guarda nada, no cifra el secreto del código (eso es de un
adaptador) ni sabe de HTTP.
"""

import base64
import hashlib
import hmac
import re
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urlencode

from app.domain.errors import InvalidRequestError

# --- Contraseñas ---------------------------------------------------------------
# Parámetros de scrypt recomendados por OWASP (2023+): N=2^15, r=8, p=1
# (~32 MiB y ~50-100 ms por intento en el servidor).
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_KEY_BYTES = 32
_SCRYPT_SALT_BYTES = 16
# Margen de memoria para OpenSSL: 128 * N * r = 32 MiB, se deja el doble.
_SCRYPT_MAXMEM = 2 * 128 * SCRYPT_N * SCRYPT_R
_SCHEME = "scrypt"
MIN_PASSWORD_CHARS = 12
MAX_PASSWORD_CHARS = 128
MIN_USERNAME_IN_PASSWORD = 4
# Contraseñas temporales: 16 caracteres de 57 posibles (~93 bits), sin letras
# que se confunden al dictarlas (0/O, 1/l/I).
TEMP_PASSWORD_CHARS = 16
_TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
# Intentos fallidos seguidos que bloquean la cuenta, y por cuánto tiempo.
MAX_USER_FAILURES = 5
USER_LOCK_MINUTES = 15

# --- Códigos de 6 dígitos (TOTP) ---------------------------------------------------
TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
# Se acepta un periodo antes y uno después (±30 s) por relojes desfasados.
TOTP_WINDOW = 1
# 20 bytes = 160 bits, lo que recomienda RFC 4226 para HMAC-SHA1.
_TOTP_SECRET_BYTES = 20
TOTP_ISSUER = "Oráculo Monitor"
_CODE = re.compile(rf"^\d{{{TOTP_DIGITS}}}$")


def hash_password(password: str) -> str:
    """Huella de una contraseña para guardarla.

    Args:
        password: La contraseña tal cual la escribió la persona.

    Returns:
        ``scrypt$N$r$p$<sal>$<huella>`` (base64). Dos llamadas con la misma
        contraseña dan textos distintos (la sal es al azar).
    """
    salt = secrets.token_bytes(_SCRYPT_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=SCRYPT_KEY_BYTES,
    )
    return "$".join(
        (
            _SCHEME,
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        )
    )


# Huella de relleno: si el usuario no existe, igual se calcula scrypt para
# que la respuesta tarde lo mismo y no revele qué usuarios existen.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def verify_password(password: str, stored: str | None) -> bool:
    """Si la contraseña corresponde a la huella guardada (tiempo constante).

    Args:
        password: Lo que escribió la persona.
        stored: La huella guardada; ``None`` si la persona no tiene contraseña.

    Returns:
        ``True`` solo si coincide. Una huella dañada o ausente da ``False``
        (pero igual se calcula scrypt, para tardar lo mismo).
    """
    try:
        scheme, n, r, p, salt_b64, digest_b64 = (stored or DUMMY_PASSWORD_HASH).split("$")
        if scheme != _SCHEME:
            return False
        expected = base64.b64decode(digest_b64)
        candidate = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=_SCRYPT_MAXMEM,
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return stored is not None and hmac.compare_digest(candidate, expected)


def validated_password(password: str, username: str) -> str:
    """Revisa que una contraseña nueva cumpla las reglas.

    Args:
        password: La contraseña nueva.
        username: El usuario (la contraseña no puede contenerlo).

    Returns:
        La misma contraseña (no se recorta: los espacios cuentan).

    Raises:
        InvalidRequestError: Si es corta, muy larga, no mezcla letras y
            números o contiene el usuario.
    """
    problems: list[str] = []
    if not MIN_PASSWORD_CHARS <= len(password) <= MAX_PASSWORD_CHARS:
        problems.append(f"Debe tener de {MIN_PASSWORD_CHARS} a {MAX_PASSWORD_CHARS} caracteres.")
    if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", password) or not re.search(r"\d", password):
        problems.append("Debe mezclar letras y números.")
    # Con usuarios muy cortos («ana») la regla rechazaría palabras comunes
    # («mañana»); solo aplica desde 4 caracteres.
    if len(username) >= MIN_USERNAME_IN_PASSWORD and username.lower() in password.lower():
        problems.append("No puede contener tu usuario.")
    if problems:
        raise InvalidRequestError(
            "La contraseña no cumple las reglas: " + " ".join(problems),
            {"problemas": [{"campo": "new_password", "mensaje": m} for m in problems]},
        )
    return password


def new_temporary_password() -> str:
    """Contraseña temporal al azar (se cambia en el primer ingreso).

    Example:
        >>> len(new_temporary_password())
        16
    """
    while True:
        candidate = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(TEMP_PASSWORD_CHARS))
        # Que cumpla las mismas reglas: al menos una letra y un número.
        if re.search(r"\d", candidate) and re.search(r"[A-Za-z]", candidate):
            return candidate


@dataclass(frozen=True, slots=True)
class TotpEnrollment:
    """Lo que se le muestra a la persona para dar de alta su Authenticator.

    Attributes:
        secret: El secreto en base32 (se puede teclear si no se escanea).
        uri: El ``otpauth://`` que va dentro del código QR.
    """

    secret: str
    uri: str


def new_totp_secret() -> str:
    """Secreto nuevo para el código de 6 dígitos, en base32 sin ``=``."""
    return base64.b32encode(secrets.token_bytes(_TOTP_SECRET_BYTES)).decode().rstrip("=")


def totp_enrollment(secret: str, username: str) -> TotpEnrollment:
    """Arma el ``otpauth://`` que entiende Microsoft Authenticator.

    Args:
        secret: Secreto en base32.
        username: Usuario, para que la persona reconozca la cuenta en su app.

    Returns:
        El secreto y la URI para el QR.
    """
    label = quote(f"{TOTP_ISSUER}:{username}")
    params = urlencode(
        {
            "secret": secret,
            "issuer": TOTP_ISSUER,
            "algorithm": "SHA1",
            "digits": TOTP_DIGITS,
            "period": TOTP_PERIOD_SECONDS,
        },
        quote_via=quote,
    )
    return TotpEnrollment(secret, f"otpauth://totp/{label}?{params}")


def totp_counter(moment: datetime) -> int:
    """El número de periodo de 30 s de un momento (para evitar repetir códigos)."""
    return int(moment.timestamp()) // TOTP_PERIOD_SECONDS


def totp_code(secret: str, counter: int) -> str:
    """El código de 6 dígitos de un periodo (RFC 4226 con contador de tiempo).

    Example:
        >>> totp_code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 1)  # vector de RFC 4226
        '287082'
    """
    padded = secret.upper() + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    # Truncado dinámico de RFC 4226 §5.3.
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**TOTP_DIGITS).zfill(TOTP_DIGITS)


def matching_totp_counter(
    secret: str, code: str, moment: datetime, last_used: int | None
) -> int | None:
    """El periodo al que corresponde un código, si es válido y no se ha usado.

    Args:
        secret: Secreto en base32.
        code: Lo que escribió la persona (se ignoran espacios).
        moment: Hora actual.
        last_used: Último periodo ya usado por esta persona (anti-repetición).

    Returns:
        El periodo del código, o ``None`` si no corresponde o ya se usó.
    """
    clean = code.replace(" ", "")
    if not _CODE.match(clean):
        return None
    now = totp_counter(moment)
    for counter in range(now - TOTP_WINDOW, now + TOTP_WINDOW + 1):
        if last_used is not None and counter <= last_used:
            continue
        if hmac.compare_digest(totp_code(secret, counter), clean):
            return counter
    return None
