"""Detección del encoding de los textos de un shapefile (CLAUDE.md §6.4).

Problema: los DBF no dicen con certeza en qué encoding están sus textos. El
archivo ``.cpg`` lo declara a veces, pero puede faltar o estar mal. Con el
encoding equivocado "Peñón" se lee como "PeÃ±Ã³n" (UTF-8 leído como
latin1) o como "Pe±¢n" (cp1252 leído como cp850).

Método: se decodifican todos los nombres con cada candidato (``utf-8``,
``cp1252``, ``latin1`` y ``cp850``, en ese orden) y se califica el resultado:
suma por cada letra esperada en español (á é í ó ú ü ñ y sus mayúsculas) y
resta por cada carácter "sospechoso" típico de una lectura equivocada
(símbolos del rango U+0080–U+00BF, Ã, Â, cajas de dibujo, controles).
Gana el que decodifica sin errores y tiene la mejor calificación; en empate
gana el primero de la lista.

No hace: no convierte archivos; solo decide y explica la decisión.
"""

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

# Orden de preferencia, el que pide CLAUDE.md §6.4.
CANDIDATES: tuple[str, ...] = ("utf-8", "cp1252", "latin1", "cp850")

EXPECTED_CHARS = frozenset("áéíóúüñÁÉÍÓÚÜÑ")
# Letras que aparecen al leer UTF-8 como si fuera latin1/cp1252 ("Ã±" = ñ).
_MOJIBAKE_LEADS = frozenset("ÃÂ")
# Símbolos de U+0080 a U+00BF (¡ ¿ y º son válidos en español y se permiten).
_SYMBOLS_RANGE = range(0x80, 0xC0)
_ALLOWED_SYMBOLS = frozenset("¡¿º")
# Cajas de dibujo, típicas de leer cp1252 como cp850.
_BOX_DRAWING_RANGE = range(0x2500, 0x2580)
# Un carácter sospechoso pesa más que una letra esperada: basta poca basura
# para descartar un encoding.
_SUSPICIOUS_WEIGHT = 3


@dataclass(frozen=True, slots=True)
class CandidateScore:
    """Resultado de probar un encoding.

    Attributes:
        encoding: Nombre del encoding.
        decodes: Si todos los valores se pudieron decodificar.
        expected: Cuántas letras esperadas en español aparecieron.
        suspicious: Cuántos caracteres sospechosos aparecieron.
    """

    encoding: str
    decodes: bool
    expected: int
    suspicious: int

    @property
    def score(self) -> int:
        """Calificación: letras esperadas menos sospechosos ponderados."""
        return self.expected - _SUSPICIOUS_WEIGHT * self.suspicious


@dataclass(frozen=True, slots=True)
class EncodingReport:
    """Decisión de encoding con su evidencia.

    Attributes:
        chosen: Encoding elegido.
        declared: Lo que dice el ``.cpg``, si existe.
        scores: Calificación de cada candidato, en orden de ``CANDIDATES``.
    """

    chosen: str
    declared: str | None
    scores: tuple[CandidateScore, ...]

    @property
    def agrees_with_declared(self) -> bool | None:
        """Si el elegido coincide con el ``.cpg`` (``None`` si no hay ``.cpg``)."""
        if self.declared is None:
            return None
        return normalize_encoding_name(self.declared) == normalize_encoding_name(self.chosen)


def normalize_encoding_name(name: str) -> str:
    """Unifica nombres de encoding ("UTF-8", "utf8", "1252", "windows-1252").

    Args:
        name: Nombre como aparece en un ``.cpg`` o en Python.

    Returns:
        Nombre canónico en minúsculas.
    """
    cleaned = name.strip().lower().replace("_", "-")
    aliases = {
        "utf8": "utf-8",
        "1252": "cp1252",
        "windows-1252": "cp1252",
        "ansi 1252": "cp1252",
        "iso-8859-1": "latin1",
        "iso8859-1": "latin1",
        "latin-1": "latin1",
        "850": "cp850",
    }
    return aliases.get(cleaned, cleaned)


def _is_suspicious(char: str) -> bool:
    code = ord(char)
    if char in _MOJIBAKE_LEADS:
        return True
    if code in _SYMBOLS_RANGE and char not in _ALLOWED_SYMBOLS:
        return True
    if code in _BOX_DRAWING_RANGE:
        return True
    return unicodedata.category(char) == "Cc"


def score_candidate(values: Iterable[bytes], encoding: str) -> CandidateScore:
    """Califica qué tan bien se leen los valores con un encoding.

    Args:
        values: Bytes crudos de los textos.
        encoding: Encoding a probar.

    Returns:
        La calificación del candidato.
    """
    expected = 0
    suspicious = 0
    for raw in values:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            return CandidateScore(encoding, decodes=False, expected=0, suspicious=0)
        for char in text:
            if char in EXPECTED_CHARS:
                expected += 1
            elif _is_suspicious(char):
                suspicious += 1
    return CandidateScore(encoding, decodes=True, expected=expected, suspicious=suspicious)


def detect_encoding(values: Iterable[bytes], declared: str | None = None) -> EncodingReport:
    """Elige el encoding más plausible para un conjunto de textos.

    Args:
        values: Bytes crudos de los textos (por ejemplo, todos los NOMGEO).
        declared: Contenido del ``.cpg``, si existe.

    Returns:
        El reporte con el encoding elegido y la evidencia de cada candidato.

    Example:
        >>> detect_encoding(["Peñón".encode("cp1252")]).chosen
        'cp1252'
    """
    materialized = list(values)
    scores = tuple(score_candidate(materialized, candidate) for candidate in CANDIDATES)
    valid = [s for s in scores if s.decodes]
    # max() conserva el primero en caso de empate, respetando el orden de preferencia.
    best = max(valid, key=lambda s: s.score)
    return EncodingReport(chosen=best.encoding, declared=declared, scores=scores)
