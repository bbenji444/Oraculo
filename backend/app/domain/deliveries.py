"""Reglas de los envíos (F12.11, ADR-0039): canales, estados, reintentos y destinatarios.

La sección «Envíos» manda lo que produce un módulo (hoy, el PDF de cada
corrida FGR) a una lista de destinatarios, según reglas que administra Benji.
Aquí viven las reglas puras:

- qué estados puede tener una guía de envío y cuándo se reintenta;
- qué regla manda a qué hora y qué día, y a quién (todos, todos menos
  algunos, o solo algunos);
- cómo se valida un destinatario;
- la llave que impide mandar dos veces lo mismo.

Está escrito sin nada del monitor para poder volverse un módulo general de
Oráculo: una «fuente» es solo un nombre (``monitor.corrida_fgr``).

No hace: no manda nada ni lee la base (eso es de los adaptadores).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.errors import DeliveryValidationError


class DeliveryChannel(StrEnum):
    """Por dónde se manda."""

    EMAIL = "email"
    WHATSAPP = "whatsapp"


class AccountProvider(StrEnum):
    """Servicio de la cuenta desde la que se manda."""

    OUTLOOK = "outlook"
    GMAIL = "gmail"
    WHATSAPP = "whatsapp"

    @property
    def channel(self) -> DeliveryChannel:
        """El canal que atiende: Outlook y Gmail son correo."""
        return (
            DeliveryChannel.WHATSAPP if self is AccountProvider.WHATSAPP else DeliveryChannel.EMAIL
        )


class RuleAudience(StrEnum):
    """A quién manda una regla."""

    ALL = "all"  # todos los destinatarios activos (menos las excepciones)
    SELECTED = "selected"  # solo los elegidos


class AccountStatus(StrEnum):
    """Estado de una cuenta de envío."""

    PENDING = "pending"  # se pidió conectar; falta que alguien autorice
    ACTIVE = "active"
    FAILED = "failed"
    DISABLED = "disabled"


class DeliveryStatus(StrEnum):
    """Estado de una guía de envío."""

    PENDING = "pending"  # por mandar (o esperando su siguiente intento)
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"  # se acabaron los intentos o el error no se arregla reintentando
    SKIPPED = "skipped"  # no se pudo ni intentar (por ejemplo, sin cuenta)


# Fuente de los reportes de las corridas automáticas del monitor FGR.
SOURCE_FGR_RUN = "monitor.corrida_fgr"
# Nombre en pantalla de cada fuente conocida (crecerá con otros módulos).
SOURCES: dict[str, str] = {SOURCE_FGR_RUN: "Monitor de noticias · reporte de la corrida FGR"}

# Esperas entre intentos (minutos): reintentar enseguida casi nunca sirve
# (plan de automatización §4.1). Con 3 esperas hay 4 intentos en total.
RETRY_DELAYS_MINUTES = (1, 5, 30)
MAX_ATTEMPTS = len(RETRY_DELAYS_MINUTES) + 1

# Correo: algo@algo.dominio, sin espacios. La validación fina la hace el proveedor.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# WhatsApp: número internacional sin «+», de 10 a 15 dígitos (52 + 10 en México).
_PHONE = re.compile(r"^\d{10,15}$")
MAX_NAME_CHARS = 120
HOURS_IN_DAY = 24
MINUTES_IN_DAY = HOURS_IN_DAY * 60
MINUTES_PER_HOUR = 60
# Días ISO: 1 = lunes … 7 = domingo.
FIRST_DAY, LAST_DAY = 1, 7
_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


def next_attempt_at(attempts: int, now: datetime) -> datetime | None:
    """Cuándo toca el siguiente intento, o ``None`` si ya no hay más.

    Args:
        attempts: Intentos ya hechos (incluido el que acaba de fallar).
        now: Momento del fallo.

    Returns:
        La hora del siguiente intento, o ``None`` si se acabaron.

    Example:
        >>> next_attempt_at(1, datetime(2026, 11, 7, 7, 5, tzinfo=UTC))
        datetime(2026, 11, 7, 7, 6, tzinfo=UTC)
    """
    if attempts >= MAX_ATTEMPTS or attempts < 1:
        return None
    return now + timedelta(minutes=RETRY_DELAYS_MINUTES[attempts - 1])


def rule_due(times: tuple[int, ...], days: tuple[int, ...], local: datetime) -> bool:
    """Si una regla manda en ese minuto (hora de la CDMX).

    Args:
        times: Minutos del día de la regla (09:30 = 570).
        days: Días ISO de la regla (1 = lunes); vacío = todos.
        local: El momento, ya en hora de la Ciudad de México.

    Returns:
        ``True`` si le toca.
    """
    minute = local.hour * MINUTES_PER_HOUR + local.minute
    return minute in times and (not days or local.isoweekday() in days)


def rule_targets[T](
    audience: RuleAudience,
    recipient_ids: Sequence[int],
    exclude_ids: Sequence[int],
    active: Sequence[tuple[int, T]],
) -> list[T]:
    """A quién manda una regla, de entre los destinatarios activos.

    Args:
        audience: Todos o solo los elegidos.
        recipient_ids: Los elegidos (si ``SELECTED``).
        exclude_ids: Las excepciones (si ``ALL``).
        active: ``(id, destinatario)`` de los destinatarios activos.

    Returns:
        Los destinatarios que reciben, en el orden de ``active``.
    """
    if audience is RuleAudience.ALL:
        return [r for rid, r in active if rid not in exclude_ids]
    return [r for rid, r in active if rid in recipient_ids]


def parse_time(text: str) -> int:
    """«09:30» → 570 (minutos del día).

    Raises:
        DeliveryValidationError: Si no es una hora válida.
    """
    match = _TIME.match(text.strip())
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour < HOURS_IN_DAY and minute < MINUTES_PER_HOUR:
            return hour * MINUTES_PER_HOUR + minute
    raise DeliveryValidationError(
        "Esa hora no es válida.",
        {"problemas": [{"campo": "times", "mensaje": f"«{text}» no es una hora (usa 09:30)."}]},
    )


def format_time(minutes: int) -> str:
    """570 → «09:30»."""
    return f"{minutes // MINUTES_PER_HOUR:02d}:{minutes % MINUTES_PER_HOUR:02d}"


def idempotency_key(
    source: str,
    source_ref: str,
    channel: DeliveryChannel,
    destination: str,
    slot: str | None = None,
) -> str:
    """La llave que impide mandar dos veces lo mismo al mismo destino.

    Args:
        source: Fuente («monitor.corrida_fgr»).
        source_ref: Cuál (el id de la corrida).
        channel: Canal.
        destination: Correo o número, ya limpio.
        slot: Hora programada sin corrida («2026-11-07 09:30»): ese reporte
            se vuelve a mandar porque alguien lo programó así.

    Returns:
        Texto único por envío.
    """
    key = f"{source}|{source_ref}|{channel.value}|{destination.lower()}"
    return f"{key}|{slot}" if slot else key


def mask_destination(destination: str) -> str:
    """Oculta parte del destino para las pantallas y los logs.

    Example:
        >>> mask_destination("benjamon_300@hotmail.com")
        'be•••@hotmail.com'
        >>> mask_destination("525512345678")
        '52••••••5678'
    """
    if "@" in destination:
        user, domain = destination.split("@", 1)
        return f"{user[:2]}•••@{domain}"
    return f"{destination[:2]}{'•' * max(len(destination) - 6, 0)}{destination[-4:]}"


@dataclass(frozen=True, slots=True)
class RecipientDraft:
    """Un destinatario validado.

    Attributes:
        name: Nombre para mostrar.
        email: Correo, en minúsculas, o ``None``.
        phone: WhatsApp, solo dígitos con lada de país, o ``None``.
        is_active: Si recibe envíos.
    """

    name: str
    email: str | None
    phone: str | None
    is_active: bool = True

    @classmethod
    def validated(
        cls, name: str, email: str | None, phone: str | None, is_active: bool = True
    ) -> "RecipientDraft":
        """Limpia y valida los datos.

        Args:
            name: Nombre.
            email: Correo (vacío = sin correo).
            phone: WhatsApp (se quitan espacios, guiones y «+»).
            is_active: Si recibe envíos.

        Returns:
            El destinatario limpio.

        Raises:
            DeliveryValidationError: Sin nombre, sin ningún contacto, o con un
                correo o número que no tienen forma válida.
        """
        problems: list[dict[str, str]] = []
        clean_name = " ".join(name.split())
        if not clean_name:
            problems.append({"campo": "name", "mensaje": "Escribe el nombre."})
        elif len(clean_name) > MAX_NAME_CHARS:
            problems.append({"campo": "name", "mensaje": f"Máximo {MAX_NAME_CHARS} caracteres."})
        clean_email = (email or "").strip().lower() or None
        if clean_email and not _EMAIL.match(clean_email):
            problems.append({"campo": "email", "mensaje": "Ese correo no parece válido."})
        clean_phone = re.sub(r"[\s\-+()]", "", phone or "") or None
        if clean_phone and not _PHONE.match(clean_phone):
            problems.append(
                {"campo": "phone", "mensaje": "Usa el número con lada de país, como 525512345678."}
            )
        if not clean_email and not clean_phone:
            problems.append({"campo": "email", "mensaje": "Pon al menos un correo o un WhatsApp."})
        if problems:
            raise DeliveryValidationError("El destinatario no es válido.", {"problemas": problems})
        return cls(clean_name, clean_email, clean_phone, is_active)


def validate_times(times: Sequence[int]) -> tuple[int, ...]:
    """Valida y ordena las horas de una regla (minutos del día).

    Raises:
        DeliveryValidationError: Si no hay ninguna o alguna no existe.
    """
    if not times:
        raise DeliveryValidationError(
            "Elige al menos una hora.",
            {"problemas": [{"campo": "times", "mensaje": "Elige al menos una hora."}]},
        )
    if any(t < 0 or t >= MINUTES_IN_DAY for t in times):
        raise DeliveryValidationError(
            "Hora inválida.", {"problemas": [{"campo": "times", "mensaje": "Hora inválida."}]}
        )
    return tuple(sorted(set(times)))


def validate_days(days: Sequence[int]) -> tuple[int, ...]:
    """Valida y ordena los días (1 = lunes … 7 = domingo); vacío = todos.

    Raises:
        DeliveryValidationError: Si algún día no existe.
    """
    if any(d < FIRST_DAY or d > LAST_DAY for d in days):
        raise DeliveryValidationError(
            "Día inválido.", {"problemas": [{"campo": "days", "mensaje": "Día inválido."}]}
        )
    unique = tuple(sorted(set(days)))
    # Los siete días son lo mismo que «todos».
    return () if len(unique) == LAST_DAY else unique
