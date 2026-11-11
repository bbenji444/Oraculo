"""Cifra el secreto del código de 6 dígitos con AES-GCM (ADR-0043).

Si alguien se robara la tabla ``users``, no podría generar los códigos de
nadie: el secreto va cifrado y la llave sale de ``AUTH_KEY_PEPPER``, que vive
en el ``.env`` del servidor, fuera de la base.

AES-GCM cifra y además autentica: si alguien altera el texto cifrado,
``open`` lo rechaza. La llave de 256 bits se deriva de la pimienta con
HKDF-SHA256 y una etiqueta propia, para no reusar la pimienta tal cual (ya se
usa para las huellas de las llaves).

No hace: no decide qué se cifra ni guarda nada.
"""

import base64
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_VERSION = "v1"
# Etiqueta de HKDF: separa esta llave de cualquier otro uso de la pimienta.
_INFO = b"monitor-noticias/totp-secret/v1"
_KEY_BYTES = 32
# 96 bits: el tamaño de nonce recomendado para AES-GCM (NIST SP 800-38D).
_NONCE_BYTES = 12


class AesGcmSecretBox:
    """``SecretBoxPort`` con AES-256-GCM.

    Args:
        pepper: Secreto del servidor (``AUTH_KEY_PEPPER``).
    """

    def __init__(self, pepper: bytes) -> None:
        key = HKDF(algorithm=hashes.SHA256(), length=_KEY_BYTES, salt=None, info=_INFO).derive(
            pepper
        )
        self._aead = AESGCM(key)

    def seal(self, plain: str) -> str:
        """Ver ``SecretBoxPort.seal``: ``v1:<base64(nonce + cifrado)>``."""
        nonce = secrets.token_bytes(_NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, plain.encode(), _VERSION.encode())
        return f"{_VERSION}:{base64.b64encode(nonce + sealed).decode()}"

    def open(self, sealed: str) -> str:
        """Ver ``SecretBoxPort.open``.

        Raises:
            ValueError: Si el texto fue alterado, está dañado o se cifró con
                otra pimienta.
        """
        version, _, payload = sealed.partition(":")
        if version != _VERSION:
            msg = "Secreto con un formato desconocido."
            raise ValueError(msg)
        try:
            raw = base64.b64decode(payload, validate=True)
            plain = self._aead.decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], _VERSION.encode())
        except (InvalidTag, ValueError) as error:
            msg = "El secreto fue alterado o se cifró con otra pimienta."
            raise ValueError(msg) from error
        return plain.decode()
