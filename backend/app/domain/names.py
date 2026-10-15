"""Normalización de nombres de lugares para compararlos.

Regla de CLAUDE.md §6.3: el nombre original se guarda intacto para
mostrarlo, y para comparar se usa una versión normalizada (``name_norm``):
mayúsculas, sin acentos, **conservando la Ñ**, sin espacios repetidos.

Esta es la **única** implementación de la regla (ADR-0008). La usan el
cargador de geodatos, el buscador de regiones y, en F4, el geocodificador,
para que todos comparen igual. No se usa ``unaccent`` de PostgreSQL porque
convierte la ñ en n (``Peñón`` → ``Penon``).

No hace: no quita signos de puntuación ni corrige errores de escritura;
eso le toca a la búsqueda difusa (trigramas).
"""

import unicodedata

# Marca diacrítica "tilde" (U+0303). Al descomponer "Ñ" en Unicode (NFD)
# queda como "N" + esta marca; es la única marca que se conserva, y solo
# cuando acompaña a una N.
_COMBINING_TILDE = "̃"


def normalize_name(name: str) -> str:
    """Normaliza un nombre de lugar para compararlo con otros.

    Pasos:
    1. Mayúsculas.
    2. Descomposición Unicode (NFD): "Ó" se vuelve "O" + acento.
    3. Se eliminan todas las marcas diacríticas excepto la tilde de la Ñ.
    4. Recomposición (NFC) y espacios: sin espacios al inicio o al final ni
       repetidos (incluye espacios no separables y tabuladores).

    Args:
        name: Nombre tal como viene de la fuente o del usuario.

    Returns:
        El nombre normalizado. Una cadena vacía o con solo espacios
        devuelve ``""``.

    Example:
        >>> normalize_name("Peñón de los  Baños")
        'PEÑON DE LOS BAÑOS'
        >>> normalize_name("Nezahualcóyotl")
        'NEZAHUALCOYOTL'
        >>> normalize_name("Güémez")
        'GUEMEZ'
    """
    decomposed = unicodedata.normalize("NFD", name.upper())
    kept: list[str] = []
    for char in decomposed:
        if unicodedata.combining(char):
            # Solo la tilde que sigue a una N sobrevive: así "Ñ" se conserva y
            # "Ã" (tilde sobre A, rara en español) se vuelve "A".
            if char == _COMBINING_TILDE and kept and kept[-1] == "N":
                kept.append(char)
            continue
        kept.append(char)
    composed = unicodedata.normalize("NFC", "".join(kept))
    return " ".join(composed.split())
