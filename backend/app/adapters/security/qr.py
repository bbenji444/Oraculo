"""Dibuja el código QR que se escanea con Microsoft Authenticator (ADR-0043).

Usa ``segno`` (Python puro). El QR va negro sobre blanco y con margen: las
cámaras lo leen mucho mejor así que con los colores oscuros de la pantalla.

No hace: no sabe qué contiene el QR.
"""

import io

import segno

# Tamaño de cada cuadrito en el SVG y nivel de corrección «M» (~15 %), el
# habitual para QR de autenticadores.
_SCALE = 5
_ERROR = "m"


class SegnoQrRenderer:
    """``QrRendererPort`` con segno."""

    def svg(self, content: str) -> str:
        """Ver ``QrRendererPort.svg``: un SVG completo, con su ``xmlns``.

        ``svg_inline`` lo omite (sirve para pegarlo dentro de HTML), pero la
        pantalla lo muestra como imagen ``data:`` y ahí, sin ``xmlns``, el
        navegador no lo dibuja.
        """
        code = segno.make(content, error=_ERROR)
        buffer = io.BytesIO()
        code.save(buffer, kind="svg", scale=_SCALE, dark="#000000", light="#ffffff", xmldecl=False)
        return buffer.getvalue().decode("utf-8")
