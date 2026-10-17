"""Similitud de títulos con rapidfuzz, para quitar notas casi duplicadas (§9).

El dominio (``app.domain.dedupe``) recibe esta función como parámetro: así
no importa librerías externas (CLAUDE.md §6.1).

No hace: no normaliza (los títulos ya llegan con ``normalize_name``).
"""

from rapidfuzz import fuzz

# rapidfuzz da la similitud de 0 a 100; el dominio la usa de 0 a 1.
_PERCENT = 100.0


def title_similarity(a: str, b: str) -> float:
    """Similitud de dos títulos normalizados, de 0 a 1.

    Usa ``fuzz.ratio`` (distancia de Levenshtein normalizada): sensible al
    orden, como debe ser para títulos casi idénticos.

    Args:
        a: Título normalizado.
        b: Otro título normalizado.

    Returns:
        1.0 si son iguales; 0.9 o más si solo cambian algunas letras.

    Example:
        >>> title_similarity("HACKEO EN IZTAPALAPA", "HACKEO A IZTAPALAPA")
        0.923...
    """
    return fuzz.ratio(a, b) / _PERCENT
