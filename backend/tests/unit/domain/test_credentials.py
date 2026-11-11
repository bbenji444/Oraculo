"""Contraseñas (scrypt) y códigos de 6 dígitos (TOTP) — reglas puras (ADR-0043)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.credentials import (
    TEMP_PASSWORD_CHARS,
    hash_password,
    matching_totp_counter,
    new_temporary_password,
    new_totp_secret,
    totp_code,
    totp_counter,
    totp_enrollment,
    validated_password,
    verify_password,
)
from app.domain.errors import InvalidRequestError

# Vector de prueba de RFC 6238 (apéndice B), secreto «12345678901234567890».
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
NOW = datetime(2026, 11, 10, 18, 0, 10, tzinfo=UTC)


def test_la_huella_no_guarda_la_contrasena_y_cambia_cada_vez() -> None:
    first = hash_password("Contraseña-segura-1")
    second = hash_password("Contraseña-segura-1")

    assert first != second
    assert "Contraseña" not in first
    assert first.startswith("scrypt$32768$8$1$")
    assert verify_password("Contraseña-segura-1", first)
    assert verify_password("Contraseña-segura-1", second)
    assert not verify_password("contraseña-segura-1", first)


@pytest.mark.parametrize(
    "stored", [None, "", "md5$abc", "scrypt$1$2$3$no-es-base64$x", "scrypt$solo$tres"]
)
def test_huella_ausente_o_danada_nunca_deja_pasar(stored: str | None) -> None:
    assert not verify_password("lo-que-sea-123", stored)


@pytest.mark.parametrize(
    ("counter", "expected"),
    # RFC 6238, apéndice B, con SHA1 y 8 dígitos; aquí se comparan los 6 últimos.
    [(59 // 30, "287082"), (1111111109 // 30, "081804"), (1234567890 // 30, "005924")],
)
def test_codigos_del_estandar(counter: int, expected: str) -> None:
    assert totp_code(RFC_SECRET, counter) == expected


def test_el_codigo_actual_y_los_vecinos() -> None:
    secret = new_totp_secret()
    now = totp_counter(NOW)

    assert matching_totp_counter(secret, totp_code(secret, now), NOW, None) == now
    assert matching_totp_counter(secret, totp_code(secret, now - 1), NOW, None) == now - 1
    assert matching_totp_counter(secret, totp_code(secret, now + 1), NOW, None) == now + 1
    assert matching_totp_counter(secret, totp_code(secret, now - 2), NOW, None) is None


def test_un_codigo_ya_usado_no_vuelve_a_servir() -> None:
    secret = new_totp_secret()
    now = totp_counter(NOW)
    code = totp_code(secret, now)

    assert matching_totp_counter(secret, code, NOW, last_used=now) is None
    assert matching_totp_counter(secret, code, NOW, last_used=now - 1) == now


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", "12 34 5"])
def test_codigos_mal_formados(code: str) -> None:
    assert matching_totp_counter(new_totp_secret(), code, NOW, None) is None


def test_los_espacios_del_codigo_no_estorban() -> None:
    secret = new_totp_secret()
    code = totp_code(secret, totp_counter(NOW))

    assert matching_totp_counter(secret, f"{code[:3]} {code[3:]}", NOW, None) is not None


def test_el_qr_lleva_lo_que_pide_microsoft_authenticator() -> None:
    enrollment = totp_enrollment("ABCDEF", "benji")

    assert enrollment.uri.startswith("otpauth://totp/Or%C3%A1culo%20Monitor%3Abenji?")
    for part in ("secret=ABCDEF", "digits=6", "period=30", "algorithm=SHA1"):
        assert part in enrollment.uri


def test_secretos_y_temporales_al_azar() -> None:
    secrets = {new_totp_secret() for _ in range(50)}
    temporaries = {new_temporary_password() for _ in range(50)}

    assert len(secrets) == 50
    assert all(len(s) == 32 for s in secrets)
    assert len(temporaries) == 50
    assert all(len(t) == TEMP_PASSWORD_CHARS for t in temporaries)
    assert all(validated_password(t, "benji") == t for t in temporaries)


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("Corta-1", "caracteres"),
        ("x" * 129 + "1", "caracteres"),
        ("solo-letras-sin-numeros", "letras y números"),
        ("123456789012345", "letras y números"),
        ("mi-usuario-BENJI-2026", "usuario"),
    ],
)
def test_reglas_de_contrasena(password: str, problem: str) -> None:
    with pytest.raises(InvalidRequestError, match=problem):
        validated_password(password, "benji")


def test_con_usuario_corto_no_se_rechazan_palabras_comunes() -> None:
    assert validated_password("Mañana-temprano-2026", "ana") == "Mañana-temprano-2026"


def test_una_contrasena_buena_pasa_tal_cual() -> None:
    assert validated_password(" Ñandú en la sierra 2026 ", "benji") == " Ñandú en la sierra 2026 "


def test_el_periodo_cambia_cada_30_segundos() -> None:
    assert totp_counter(NOW + timedelta(seconds=30)) == totp_counter(NOW) + 1
