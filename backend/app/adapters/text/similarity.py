"""Similitud de títulos con rapidfuzz: notas casi duplicadas (§9) e historias (F12.1c).

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


def title_token_similarity(a: str, b: str) -> float:
    """Parecido por palabras de dos títulos normalizados, de 0 a 1 (historias, F12.1c).

    Usa ``fuzz.token_set_ratio``: ignora el orden y las palabras de más, así
    «Balacera en Iztapalapa deja dos muertos» y «Dos muertos por balacera en
    Ermita Iztapalapa» salen parecidos aunque ``title_similarity`` no.

    Args:
        a: Título normalizado.
        b: Otro título normalizado.

    Returns:
        1.0 si uno contiene todas las palabras del otro.
    """
    return fuzz.token_set_ratio(a, b) / _PERCENT
