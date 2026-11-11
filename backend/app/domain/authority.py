"""Quién actúa en cada nota y la regla de relevancia «FGR federal» (F12.5, ADR-0030).

El monitor FGR solo debe contar las notas donde **actúa la FGR federal**
(detiene, catea, acusa, obtiene una sentencia, asegura) y no las de una
fiscalía estatal ni las que solo nombran a la FGR de pasada. La IA dice
quién actúa al clasificar cada nota (``articles.authority``) y el concepto
FGR lleva la regla ``fgr_federal`` (``concepts.relevance_rule``).

La relevancia final es la que dio la IA al leer la nota, **salvo** que el
concepto tenga esa regla y la nota diga que no actuó la FGR. Si no se sabe
quién actúa (``sin_dato`` o sin clasificar), se respeta lo que dijo la IA:
nada se esconde por falta de datos.

No hace: no llama a la IA ni lee la base. El SQL que aplica la regla se arma
con estas constantes en ``adapters/persistence/article_rows.py``.
"""

from enum import StrEnum


class Authority(StrEnum):
    """Quién actúa en el hecho principal de la nota (valores de ``articles.authority``)."""

    FGR = "fgr"
    """La FGR federal, el Ministerio Público Federal, la AIC o una fiscalía
    especializada federal; o alguien queda «a disposición de la FGR»."""
    FGR_MENTION = "fgr_mencion"
    """La FGR solo se nombra: le piden algo, le mandan oficios, opinan de ella."""
    STATE = "estatal"
    """Solo actúa una fiscalía o procuraduría estatal."""
    OTHER = "otra"
    """Otra autoridad, ninguna, o una fiscalía de otro país."""
    UNKNOWN = "sin_dato"
    """El título y el resumen no alcanzan para saberlo."""


class RelevanceRule(StrEnum):
    """Regla de relevancia de un concepto (valores de ``concepts.relevance_rule``)."""

    GENERAL = "general"
    """La relevancia es la que dio la IA al leer la nota."""
    FGR_FEDERAL = "fgr_federal"
    """Además, la FGR federal tiene que actuar en la nota (plan F12 §4.5)."""


# Quién actúa en las notas que la regla FGR federal deja fuera, con la razón
# que se muestra en lugar de la de la IA (es lo que lee el analista).
FGR_FEDERAL_EXCLUDED: dict[Authority, str] = {
    Authority.FGR_MENTION: "La FGR solo se menciona; no actúa en el hecho.",
    Authority.STATE: "Actúa una fiscalía estatal, no la FGR.",
    Authority.OTHER: "No actúa la FGR: es otra autoridad.",
}

AUTHORITY_LABEL: dict[Authority, str] = {
    Authority.FGR: "FGR federal",
    Authority.FGR_MENTION: "FGR solo mencionada",
    Authority.STATE: "Fiscalía estatal",
    Authority.OTHER: "Otra autoridad",
    Authority.UNKNOWN: "No se sabe",
}


def parse_authority(value: str | None) -> Authority | None:
    """Lee quién actúa desde la respuesta de la IA o la base.

    Args:
        value: Texto como ``"estatal"``; cualquier otro valor o ``None`` se
            toma como desconocido.

    Returns:
        El valor, ``Authority.UNKNOWN`` si no se reconoce, o ``None`` si no
        vino nada.
    """
    if value is None:
        return None
    try:
        return Authority(value.strip().lower())
    except ValueError:
        return Authority.UNKNOWN


# Confianza mínima para que un «sí es relevante» de la IA cuente (Benji,
# 11/11/2026: «sé mucho más estricto»). Por debajo, la IA misma dice que el
# tema es secundario o dudoso (enrich_v4 pide menos de 0.6 en ese caso).
MIN_RELEVANCE_SCORE = 0.6
LOW_CONFIDENCE_REASON = "La IA no está segura de que sea el asunto principal de la nota."


def effective_relevance(
    ai_relevant: bool,
    ai_reason: str | None,
    rule: RelevanceRule,
    authority: Authority | None,
    score: float | None = None,
) -> tuple[bool, str | None]:
    """Relevancia final de una nota para un concepto, con su razón.

    Args:
        ai_relevant: Lo que dijo la IA al leer la nota.
        ai_reason: Su razón.
        rule: Regla del concepto.
        authority: Quién actúa (``None`` si la nota no se ha clasificado).
        score: Confianza de la IA (0 a 1), si se conoce.

    Returns:
        ``(relevante, razón)``. Cambia cuando la regla es ``fgr_federal`` y la
        nota dice que no actuó la FGR, o cuando la IA dijo que sí pero con
        menos de ``MIN_RELEVANCE_SCORE`` de confianza.

    Example:
        >>> effective_relevance(True, "Menciona a la FGR", RelevanceRule.FGR_FEDERAL,
        ...                     Authority.STATE)
        (False, 'Actúa una fiscalía estatal, no la FGR.')
    """
    if rule is RelevanceRule.FGR_FEDERAL and authority in FGR_FEDERAL_EXCLUDED:
        return False, FGR_FEDERAL_EXCLUDED[authority]
    if ai_relevant and score is not None and score < MIN_RELEVANCE_SCORE:
        return False, LOW_CONFIDENCE_REASON
    return ai_relevant, ai_reason
