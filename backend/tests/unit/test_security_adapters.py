"""Adaptadores de seguridad: el QR de Microsoft Authenticator y el cifrado (ADR-0043)."""

import xml.etree.ElementTree as ET

import pytest

from app.adapters.security.qr import SegnoQrRenderer
from app.adapters.security.secret_box import AesGcmSecretBox

SVG_NS = "http://www.w3.org/2000/svg"
PEPPER = b"pimienta-de-prueba-con-mas-de-32-caracteres"


def test_el_qr_es_un_svg_completo_que_el_navegador_puede_dibujar() -> None:
    # Bug del 10/11/2026: el SVG «para incrustar» no traía xmlns y, mostrado
    # como imagen data:, el navegador no lo dibujaba.
    svg = SegnoQrRenderer().svg("otpauth://totp/Prueba:benji?secret=JBSWY3DPEHPK3PXP")

    root = ET.fromstring(svg)  # noqa: S314 — SVG generado por nosotros, no entrada externa

    assert root.tag == f"{{{SVG_NS}}}svg"
    assert not svg.startswith("<?xml")
    assert "#fff" in svg.lower()


def test_el_cifrado_va_y_vuelve_y_no_deja_el_texto_a_la_vista() -> None:
    box = AesGcmSecretBox(PEPPER)

    sealed = box.seal("JBSWY3DPEHPK3PXP")

    assert sealed.startswith("v1:")
    assert "JBSWY3DPEHPK3PXP" not in sealed
    assert box.open(sealed) == "JBSWY3DPEHPK3PXP"


def test_el_cifrado_rechaza_lo_alterado_o_de_otra_pimienta() -> None:
    sealed = AesGcmSecretBox(PEPPER).seal("SECRETO")

    with pytest.raises(ValueError, match="otra pimienta"):
        AesGcmSecretBox(b"x" * 40).open(sealed)
    with pytest.raises(ValueError, match="formato"):
        AesGcmSecretBox(PEPPER).open("sin-version")
