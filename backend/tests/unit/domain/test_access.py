"""Reglas puras de las llaves de acceso (ADR-0042): formato, huella y validaciones."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.access import (
    KEY_PREFIX,
    SECRET_CHARS,
    AuthUser,
    KeyRecord,
    Role,
    digests_match,
    key_digest,
    new_key,
    new_session_token,
    public_id_of,
    session_digest,
    validated_display_name,
    validated_email,
    validated_username,
)
from app.domain.errors import InvalidRequestError

PEPPER = b"p" * 40
NOW = datetime(2026, 11, 10, 18, tzinfo=UTC)
BENJI = AuthUser(1, "benji", "Benjamin", Role.SUPERUSER)


def test_la_llave_tiene_el_formato_de_las_apis_conocidas() -> None:
    key = new_key()

    assert key.full.startswith(KEY_PREFIX)
    assert len(key.full) == len(KEY_PREFIX) + 8 + 1 + SECRET_CHARS
    assert public_id_of(key.full) == key.public_id
    assert key.masked == f"{KEY_PREFIX}{key.public_id}…"
    assert key.full not in key.masked


def test_dos_llaves_nunca_se_repiten() -> None:
    keys = {new_key().full for _ in range(200)}

    assert len(keys) == 200


@pytest.mark.parametrize(
    "text",
    [
        "",
        "orc_live_",
        "sk-proj-abc",
        "orc_live_ABCDEFG_" + "a" * SECRET_CHARS,  # parte pública de 7
        "orc_live_ABCDEFGH_" + "a" * (SECRET_CHARS - 1),
        "orc_live_ABCDEFGH_" + "a" * (SECRET_CHARS - 1) + "!",
        "orc_test_ABCDEFGH_" + "a" * SECRET_CHARS,
    ],
)
def test_una_llave_mal_formada_se_rechaza_sin_consultar(text: str) -> None:
    assert public_id_of(text) is None


def test_espacios_alrededor_al_pegar_no_estorban() -> None:
    key = new_key()

    assert public_id_of(f"  {key.full}\n") == key.public_id
    assert key_digest(f" {key.full} ", PEPPER) == key_digest(key.full, PEPPER)


def test_la_huella_depende_de_la_pimienta_y_no_revela_la_llave() -> None:
    key = new_key().full

    digest = key_digest(key, PEPPER)

    assert len(digest) == 64
    assert key not in digest
    assert digest != key_digest(key, b"q" * 40)
    assert digests_match(digest, key_digest(key, PEPPER))
    assert not digests_match(digest, key_digest(new_key().full, PEPPER))


def test_la_sesion_se_guarda_como_huella() -> None:
    token = new_session_token()

    assert len(token) >= 43
    assert session_digest(token) != token
    assert session_digest(token) == session_digest(token)


def _record(
    *,
    user_active: bool = True,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> KeyRecord:
    return KeyRecord(1, "h", BENJI, user_active, expires_at, revoked_at)


def test_cuando_una_llave_deja_entrar() -> None:
    assert _record().usable(NOW)
    assert _record(expires_at=NOW + timedelta(days=1)).usable(NOW)
    assert not _record(expires_at=NOW).usable(NOW)
    assert not _record(revoked_at=NOW - timedelta(minutes=1)).usable(NOW)
    assert not _record(user_active=False).usable(NOW)


def test_usuario_valido_en_minusculas() -> None:
    assert validated_username("  Ana.Lopez ") == "ana.lopez"


@pytest.mark.parametrize("bad", ["", "   ", "ana lopez", "-ana", "ána", "a" * 61, "ana@x"])
def test_usuario_invalido(bad: str) -> None:
    with pytest.raises(InvalidRequestError):
        validated_username(bad)


def test_nombre_y_correo() -> None:
    assert validated_display_name("  Ana   López ") == "Ana López"
    assert validated_email(" Ana@Ovitech.MX ") == "ana@ovitech.mx"
    assert validated_email("") is None
    assert validated_email(None) is None
    with pytest.raises(InvalidRequestError):
        validated_display_name("  ")
    with pytest.raises(InvalidRequestError):
        validated_email("no-es-correo")
