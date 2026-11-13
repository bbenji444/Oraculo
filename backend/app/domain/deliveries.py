"""Reglas de los envíos (F12.11, ADR-0039): canales, estados, reintentos y destinatarios.

La sección «Envíos» manda lo que produce un módulo (hoy, el PDF de cada
corrida FGR) a todos los destinatarios activos. Solo la administra el equipo
interno: no hay envíos ni horarios distintos por persona (Benji, 06/11/2026,
ADR-0040); el horario de las corridas está en ``app.domain.schedule``.
Aquí viven las reglas puras:

- qué estados puede tener una guía de envío y cuándo se reintenta;
- cómo se valida un destinatario;
- la llave que impide mandar dos veces lo mismo.

Está escrito sin nada del monitor para poder volverse un módulo general de
Oráculo: una «fuente» es solo un nombre (``monitor.corrida_fgr``).

No hace: no manda nada ni lee la base (eso es de los adaptadores).
"""

import re
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
# El valor se quedó «corrida_fgr» por el historial; desde ADR-0046 cubre las
# corridas de todos los envíos programados, no solo la FGR.
SOURCES: dict[str, str] = {SOURCE_FGR_RUN: "Monitor de noticias · reporte de corrida automática"}

# Esperas entre intentos (minutos): reintentar enseguida casi nunca sirve
# (plan de automatización §4.1). Con 3 esperas hay 4 intentos en total.
RETRY_DELAYS_MINUTES = (1, 5, 30)
MAX_ATTEMPTS = len(RETRY_DELAYS_MINUTES) + 1
# Una guía «enviando» por más de esto se cortó a medias: el servidor se
# reinició mientras salía. Un correo con el PDF tarda unos 2 s en salir
# (medido en la VM el 12/11/2026), así que 15 minutos sobran.
STUCK_SENDING_MINUTES = 15
# Lo que queda en el historial del intento cortado.
INTERRUPTED_ERROR = "El envío se cortó a medias (el servidor se reinició); se reintenta."

# Correo: algo@algo.dominio, sin espacios. La validación fina la hace el proveedor.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# WhatsApp: número internacional sin «+», de 10 a 15 dígitos (52 + 10 en México).
_PHONE = re.compile(r"^\d{10,15}$")
MAX_NAME_CHARS = 120
# Correos por usuario normal (Benji, 10/11/2026: «uno o máximo dos»). El
# superusuario no tiene tope.
MAX_RECIPIENTS_PER_USER = 2
# Dueño de los destinatarios y envíos que existían antes de los envíos por
# usuario (migración 0042): el superusuario que los dio de alta.
DEFAULT_OWNER = "benji"


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


def idempotency_key(
    source: str, source_ref: str, channel: DeliveryChannel, destination: str
) -> str:
    """La llave que impide mandar dos veces lo mismo al mismo destino.

    Args:
        source: Fuente («monitor.corrida_fgr»).
        source_ref: Cuál (el id de la corrida).
        channel: Canal.
        destination: Correo o número, ya limpio.

    Returns:
        Texto único por envío.
    """
    return f"{source}|{source_ref}|{channel.value}|{destination.lower()}"


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
