"""Reglas para reconocer a la misma entidad escrita de otra forma (Fase 9.5, §9.8).

Dentro de un caso, la IA puede proponer a la misma persona varias veces:
"Julián “N”" en una nota, "Julián N" en otra, "Micky Hair" como alias. Este
módulo dice cómo se comparan esos nombres, cuándo se **sugiere** unirlos y
qué reglas cumple una fusión o una separación que decide una persona.

- ``entity_name_norm``: el nombre de comparación de una entidad
  (``entities.label_norm`` y ``entity_aliases.alias_norm``). Es la regla del
  proyecto (``normalize_name``) más una cosa: las comillas no cuentan.
- ``MergeReason``: por qué el sistema cree que dos entidades son la misma
  (decisión D2). La consulta vive en el repositorio; aquí, los motivos y su
  orden.
- ``check_merge`` y ``check_split``: lo que se exige antes de fusionar o de
  separar menciones (D4 y D5).

Quién lo usa: la revisión de propuestas de la IA (``entity_extraction``), el
repositorio de entidades y los casos de uso de fusión y vínculos.

No hace: no fusiona nada. Unir dos entidades siempre lo decide una persona;
el sistema solo sugiere (ADR-0104).
"""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import EntityMergeError
from app.domain.investigation import EntityType, ReviewStatus
from app.domain.names import normalize_name

# Comillas rectas y tipográficas. En las notas mexicanas a un detenido se le
# nombra "Julián “N”", y cada medio usa otras comillas ('N', «N», "N"): si
# contaran, la misma persona quedaría en varias sugerencias (bug de la 9.4).
# Se cambian por un espacio, no se borran, para que "Julián“N”" tampoco pegue
# las palabras. La migración 0021 aplica esta misma lista a lo ya guardado.
_QUOTES_TO_SPACE = str.maketrans(dict.fromkeys("\"'“”«»‘’„", " "))

# Parecido mínimo (trigramas de pg_trgm, de 0 a 1) para sugerir que dos
# nombres distintos son la misma entidad. Lo fija el plan (§9.8) y el
# ADR-0104. Medido en el caso real (21/10/2026): atrapa «…DE LA CIUDAD DE
# MÉXICO» contra «…DE CIUDAD DE MÉXICO» (0.93) y deja fuera nombres que solo
# comparten apellidos.
TRIGRAM_MERGE_THRESHOLD = 0.9


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


class MergeReason(StrEnum):
    """Por qué el sistema sugiere que dos entidades del caso son la misma (D2).

    El orden de la clase es el de la lista: primero lo más seguro.
    """

    # El mismo nombre de comparación ("Julián “N”" y "Julián N").
    SAME_NAME = "same_name"
    # Un nombre o alias de una es nombre o alias de la otra ("Micky Hair").
    SHARED_NAME = "shared_name"
    # Nombres distintos pero muy parecidos (trigramas ≥ 0.9).
    SIMILAR_NAME = "similar_name"


MERGE_REASON_LABEL: dict[MergeReason, str] = {
    MergeReason.SAME_NAME: "mismo nombre",
    MergeReason.SHARED_NAME: "nombre o alias en común",
    MergeReason.SIMILAR_NAME: "nombre parecido",
}
_REASON_RANK = {reason: rank for rank, reason in enumerate(MergeReason)}


def strongest_reason(reasons: Collection[MergeReason]) -> MergeReason:
    """El motivo más seguro de una sugerencia que cumple varios.

    Args:
        reasons: Motivos que cumple el par (al menos uno).

    Returns:
        El primero en el orden de ``MergeReason``.

    Raises:
        ValueError: Si no hay ningún motivo.
    """
    if not reasons:
        raise ValueError("Una sugerencia de fusión necesita al menos un motivo.")
    return min(reasons, key=_REASON_RANK.__getitem__)


def ordered_ids(first: int, second: int) -> tuple[int, int]:
    """Las dos entidades de un par con el id menor primero.

    Así se guarda un «No son la misma» (``entity_merge_dismissals``): A–B y
    B–A son el mismo descarte.

    Args:
        first: Una entidad.
        second: La otra.

    Returns:
        ``(menor, mayor)``.

    Raises:
        EntityMergeError: Si son la misma entidad.
    """
    if first == second:
        raise EntityMergeError("Elige dos entidades distintas.", {"entity_id": first})
    return min(first, second), max(first, second)


@dataclass(frozen=True, slots=True)
class MergeCandidate:
    """Lo que hace falta saber de una entidad para fusionarla.

    Attributes:
        entity_id: Entidad.
        type: Tipo.
        review_status: Si está sugerida, confirmada o descartada.
        merged_into: En qué otra entidad está fusionada, si lo está.
    """

    entity_id: int
    type: EntityType
    review_status: ReviewStatus
    merged_into: int | None


def check_merge(keep: MergeCandidate, merge: MergeCandidate) -> None:
    """Valida una fusión que pidió una persona (decisión D4).

    ``merge`` pasa a ser parte de ``keep``: sus menciones y alias se ven en
    ``keep`` y la fusión se puede deshacer. Las dos deben ser entidades
    "raíz" (no fusionadas en otra): así nunca se forma un ciclo.

    Args:
        keep: La entidad que queda.
        merge: La que se une a ella.

    Raises:
        EntityMergeError: Si son la misma, de tipos distintos, alguna está
            descartada, alguna ya está fusionada en otra o quedaría la
            sugerida en lugar de la confirmada.
    """
    ordered_ids(keep.entity_id, merge.entity_id)
    details: dict[str, object] = {"keep_id": keep.entity_id, "merge_id": merge.entity_id}
    if keep.type is not merge.type:
        raise EntityMergeError(
            "Solo se unen entidades del mismo tipo (una persona con una persona).", details
        )
    if ReviewStatus.DISCARDED in (keep.review_status, merge.review_status):
        raise EntityMergeError(
            "Una entidad descartada no se une: primero hay que revisarla de nuevo.", details
        )
    if keep.merged_into is not None or merge.merged_into is not None:
        raise EntityMergeError(
            "Una de las dos ya está unida a otra entidad: úsala a ella.", details
        )
    # Si quedara la sugerida, lo ya confirmado dejaría de verse en el muro
    # hasta que alguien lo volviera a confirmar.
    if (keep.review_status, merge.review_status) == (
        ReviewStatus.SUGGESTED,
        ReviewStatus.CONFIRMED,
    ):
        raise EntityMergeError("Debe quedar la entidad confirmada; une la otra a ella.", details)


def check_split(selected: Collection[int], available: Collection[int]) -> None:
    """Valida qué menciones se separan de una entidad (decisión D5).

    Sirve cuando una sugerencia juntó a dos personas distintas con el mismo
    nombre: las menciones elegidas forman una entidad nueva.

    Args:
        selected: Menciones que se separan.
        available: Menciones propias de la entidad (sin las de entidades
            unidas a ella: esas se separan deshaciendo la fusión).

    Raises:
        EntityMergeError: Si no se eligió ninguna, si alguna no es de la
            entidad o si se eligen todas (no quedaría nada).
    """
    chosen, own = set(selected), set(available)
    if not chosen:
        raise EntityMergeError("Elige al menos una mención para separar.", {})
    if not chosen <= own:
        raise EntityMergeError(
            "Solo se separan menciones propias de esta entidad.",
            {"mention_ids": sorted(chosen - own)},
        )
    if chosen == own:
        raise EntityMergeError(
            "Si se separan todas las menciones no queda nada: deja al menos una.", {}
        )
