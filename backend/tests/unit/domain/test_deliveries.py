"""Reglas de los envíos (ADR-0039): reintentos, horas, llaves y destinatarios."""

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from app.domain.deliveries import (
    MAX_ATTEMPTS,
    AccountProvider,
    DeliveryChannel,
    RecipientDraft,
    idempotency_key,
    mask_destination,
    next_attempt_at,
)
from app.domain.errors import DeliveryValidationError

NOW = datetime(2026, 11, 7, 13, 5, tzinfo=UTC)


def test_los_reintentos_aguantan_unas_8_horas_y_luego_ya_no() -> None:
    """12/11/2026: Outlook falló de 15:00 a casi medianoche; 36 minutos no alcanzaban."""
    assert next_attempt_at(1, NOW) == NOW + timedelta(minutes=1)
    assert next_attempt_at(2, NOW) == NOW + timedelta(minutes=5)
    total = timedelta()
    for attempt in range(1, MAX_ATTEMPTS):
        retry = next_attempt_at(attempt, NOW)
        assert retry is not None
        total += retry - NOW
    # De la primera falla al último intento: cerca de 8 horas, lo que hay entre
    # una corrida y la siguiente.
    assert timedelta(hours=7) <= total <= timedelta(hours=8)
    assert next_attempt_at(MAX_ATTEMPTS, NOW) is None
    assert next_attempt_at(0, NOW) is None


def test_la_llave_no_distingue_mayusculas_del_destino() -> None:
    a = idempotency_key("monitor.corrida_fgr", "s1", DeliveryChannel.EMAIL, "Benji@Hotmail.com")
    b = idempotency_key("monitor.corrida_fgr", "s1", DeliveryChannel.EMAIL, "benji@hotmail.com")
    assert a == b
    assert a != idempotency_key(
        "monitor.corrida_fgr", "s2", DeliveryChannel.EMAIL, "benji@hotmail.com"
    )


def test_el_destino_se_enmascara() -> None:
    assert mask_destination("benjamon_300@hotmail.com") == "be•••@hotmail.com"
    assert mask_destination("525512345678") == "52••••••5678"


def test_destinatario_limpio() -> None:
    draft = RecipientDraft.validated(
        "  Benjamin   Oviedo ", " Benji@Hotmail.COM ", "+52 55-1234-5678"
    )

    assert (draft.name, draft.email, draft.phone) == (
        "Benjamin Oviedo",
        "benji@hotmail.com",
        "525512345678",
    )


def test_destinatario_invalido_junta_todos_los_problemas() -> None:
    with pytest.raises(DeliveryValidationError) as error:
        RecipientDraft.validated(" ", "no-es-correo", "123")

    problems = cast(list[dict[str, str]], error.value.details["problemas"])
    assert [p["campo"] for p in problems] == ["name", "email", "phone"]


def test_destinatario_sin_ningun_contacto() -> None:
    with pytest.raises(DeliveryValidationError, match="no es válido"):
        RecipientDraft.validated("Ana", "", None)


def test_outlook_y_gmail_son_correo() -> None:
    assert AccountProvider.OUTLOOK.channel is DeliveryChannel.EMAIL
    assert AccountProvider.GMAIL.channel is DeliveryChannel.EMAIL
    assert AccountProvider.WHATSAPP.channel is DeliveryChannel.WHATSAPP
