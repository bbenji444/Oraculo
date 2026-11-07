"""Reglas de los envíos (ADR-0039): reintentos, horas, llaves y destinatarios."""

from datetime import UTC, datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from app.domain.deliveries import (
    MAX_ATTEMPTS,
    AccountProvider,
    DeliveryChannel,
    RecipientDraft,
    RuleAudience,
    format_time,
    idempotency_key,
    mask_destination,
    next_attempt_at,
    parse_time,
    rule_due,
    rule_targets,
    validate_days,
    validate_times,
)
from app.domain.errors import DeliveryValidationError

NOW = datetime(2026, 11, 7, 13, 5, tzinfo=UTC)


def test_reintentos_a_1_5_y_30_minutos_y_luego_ya_no() -> None:
    assert next_attempt_at(1, NOW) == NOW + timedelta(minutes=1)
    assert next_attempt_at(2, NOW) == NOW + timedelta(minutes=5)
    assert next_attempt_at(3, NOW) == NOW + timedelta(minutes=30)
    assert next_attempt_at(MAX_ATTEMPTS, NOW) is None
    assert next_attempt_at(0, NOW) is None


def test_una_regla_manda_en_su_minuto_y_sus_dias() -> None:
    friday_0930 = datetime(2026, 11, 6, 9, 30, tzinfo=ZoneInfo("America/Mexico_City"))
    assert rule_due((570,), (), friday_0930)
    assert rule_due((570,), (5,), friday_0930)
    assert not rule_due((570,), (6, 7), friday_0930)
    assert not rule_due((420,), (), friday_0930)


def test_a_quien_manda_una_regla() -> None:
    active = [(1, "Benjamin"), (2, "Geovanni"), (3, "Tadeo")]

    assert rule_targets(RuleAudience.ALL, (), (3,), active) == ["Benjamin", "Geovanni"]
    assert rule_targets(RuleAudience.SELECTED, (2, 9), (), active) == ["Geovanni"]


def test_horas_como_texto() -> None:
    assert parse_time("9:30") == 570
    assert format_time(570) == "09:30"
    for bad in ("25:00", "09:61", "nueve"):
        with pytest.raises(DeliveryValidationError):
            parse_time(bad)


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


def test_horas_y_dias_validos() -> None:
    assert validate_times((900, 420, 900)) == (420, 900)
    assert validate_days((5, 1, 5)) == (1, 5)
    assert validate_days((1, 2, 3, 4, 5, 6, 7)) == ()
    with pytest.raises(DeliveryValidationError, match="al menos una hora"):
        validate_times(())
    with pytest.raises(DeliveryValidationError):
        validate_times((1440,))
    with pytest.raises(DeliveryValidationError):
        validate_days((8,))


def test_la_llave_de_una_hora_sin_corrida_lleva_su_hora() -> None:
    plain = idempotency_key("monitor.corrida_fgr", "s1", DeliveryChannel.EMAIL, "b@x.mx")
    slotted = idempotency_key(
        "monitor.corrida_fgr", "s1", DeliveryChannel.EMAIL, "b@x.mx", "2026-11-07 09:30"
    )
    assert slotted == f"{plain}|2026-11-07 09:30"


def test_outlook_y_gmail_son_correo() -> None:
    assert AccountProvider.OUTLOOK.channel is DeliveryChannel.EMAIL
    assert AccountProvider.GMAIL.channel is DeliveryChannel.EMAIL
    assert AccountProvider.WHATSAPP.channel is DeliveryChannel.WHATSAPP
