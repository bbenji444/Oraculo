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


def test_reintentos_a_1_5_y_30_minutos_y_luego_ya_no() -> None:
    assert next_attempt_at(1, NOW) == NOW + timedelta(minutes=1)
    assert next_attempt_at(2, NOW) == NOW + timedelta(minutes=5)
    assert next_attempt_at(3, NOW) == NOW + timedelta(minutes=30)
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
