"""Reglas para reconocer a la misma entidad escrita de otra forma (Fase 9.5, §9.8).

Dentro de un caso, la IA puede proponer a la misma persona varias veces:
"Julián “N”" en una nota, "Julián N" en otra, "Micky Hair" como alias. Este
módulo dice cómo se comparan esos nombres.

- ``entity_name_norm``: el nombre de comparación de una entidad
  (``entities.label_norm`` y ``entity_aliases.alias_norm``). Es la regla del
  proyecto (``normalize_name``) más una cosa: las comillas no cuentan.

Quién lo usa: la revisión de propuestas de la IA (``entity_extraction``) y el
repositorio de entidades al agrupar sugerencias.

No hace: no fusiona nada. Unir dos entidades siempre lo decide una persona
(ADR-0104).
"""

from app.domain.names import normalize_name

# Comillas rectas y tipográficas. En las notas mexicanas a un detenido se le
# nombra "Julián “N”", y cada medio usa otras comillas ('N', «N», "N"): si
# contaran, la misma persona quedaría en varias sugerencias (bug de la 9.4).
# Se cambian por un espacio, no se borran, para que "Julián“N”" tampoco pegue
# las palabras. La migración 0021 aplica esta misma lista a lo ya guardado.
_QUOTES_TO_SPACE = str.maketrans(dict.fromkeys("\"'“”«»‘’„", " "))


def entity_name_norm(name: str) -> str:
    """Nombre de comparación de una entidad o de un alias.

    Args:
        name: Nombre como lo escribió la nota.

    Returns:
        Mayúsculas, sin acentos, con Ñ, sin comillas y sin espacios repetidos.
        Un nombre hecho solo de comillas o espacios devuelve ``""``.

    Example:
        >>> entity_name_norm("Julián “N”")
        'JULIAN N'
    """
    return normalize_name(name.translate(_QUOTES_TO_SPACE))
