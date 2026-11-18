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

Aquí también están el umbral de confianza (``MIN_RELEVANCE_SCORE``) y las
bandas de puntaje que la API manda con cada juicio (``relevance_band``,
ADR-0114): relevante, por confirmar, cercana y ajena en los conceptos
abiertos; en los exactos (el monitor FGR) solo relevante y cercana.

No hace: no llama a la IA ni lee la base. El SQL que aplica la regla se arma
con estas constantes en ``adapters/persistence/article_rows.py``.
"""

from enum import StrEnum

from app.domain.concept import QueryMode


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
# tema es secundario o dudoso (enrich_v4 y enrich_v5 piden menos de 0.6 en ese caso).
MIN_RELEVANCE_SCORE = 0.6
LOW_CONFIDENCE_REASON = "La IA no está segura de que sea el asunto principal de la nota."
# Bandas de puntaje (contrato del 18/11/2026, ADR-0114; las escribe
# enrich_v6 para los conceptos abiertos). Desde 0.8 la nota es relevante
# segura; entre MIN_RELEVANCE_SCORE y este valor, relevante «por confirmar».
CONFIRMED_RELEVANCE_SCORE = 0.8
# Desde este puntaje una no relevante es del mismo tema («cercana»); por
# debajo no tiene nada que ver («ajena»). Medido en la VM el 18/11/2026: 275
# de 401 «no» de los conceptos abiertos tenían 0.2 o menos; eran la basura
# que Benji veía en «No relevantes».
MIN_RELATED_SCORE = 0.3


class RelevanceBand(StrEnum):
    """Banda de un juicio (``relevance_band`` en la API, ADR-0114)."""

    RELEVANT = "relevant"
    """Relevante con ``CONFIRMED_RELEVANCE_SCORE`` o más (en un concepto
    exacto, cualquier relevante)."""
    UNCONFIRMED = "unconfirmed"
    """Relevante «por confirmar»: de ``MIN_RELEVANCE_SCORE`` a menos de 0.8.
    Solo en los conceptos abiertos."""
    RELATED = "related"
    """No relevante pero del mismo tema («cercana»): ``MIN_RELATED_SCORE`` o más
    (en un concepto exacto, cualquier no relevante)."""
    UNRELATED = "unrelated"
    """No tiene nada que ver con lo pedido («ajena»): menos de
    ``MIN_RELATED_SCORE``. Solo en los conceptos abiertos."""


def relevance_band(is_relevant: bool, score: float, query_mode: QueryMode) -> RelevanceBand:
    """La banda de un juicio, con la relevancia final ya aplicada.

    Se parte de la relevancia final (``effective_relevance``) y no solo del
    puntaje: una nota de una fiscalía estatal puede tener 0.9 y no ser
    relevante para la FGR. Esa cuenta como cercana: es del tema, pero no lo
    que se pidió.

    Las cuatro bandas solo valen en los conceptos abiertos, porque solo su
    prompt (``enrich_v6_open.md``) las pide. Los exactos (el monitor FGR, los
    temas) usan el texto de ``enrich_v5``, donde casi todo «no» lleva de 0 a
    0.2: con las bandas de los abiertos todos saldrían «ajenos» y la pantalla
    no los mostraría ni con «Incluir las no relevantes» (medido en la base de
    desarrollo el 18/11/2026: 2,020 de 2,021 no relevantes de la FGR tenían
    menos de 0.3). Por eso en un exacto relevante es ``relevant`` y no
    relevante es ``related``, como antes de las bandas.

    Args:
        is_relevant: Relevancia final (umbral y regla del concepto aplicados).
        score: Puntaje de la IA, de 0 a 1.
        query_mode: Modo del concepto del juicio.

    Returns:
        La banda.

    Example:
        >>> relevance_band(True, 0.7, QueryMode.OPEN)
        <RelevanceBand.UNCONFIRMED: 'unconfirmed'>
        >>> relevance_band(False, 0.45, QueryMode.OPEN)
        <RelevanceBand.RELATED: 'related'>
        >>> relevance_band(False, 0.1, QueryMode.OPEN)
        <RelevanceBand.UNRELATED: 'unrelated'>
        >>> relevance_band(False, 0.0, QueryMode.EXACT)
        <RelevanceBand.RELATED: 'related'>
    """
    if query_mode is not QueryMode.OPEN:
        return RelevanceBand.RELEVANT if is_relevant else RelevanceBand.RELATED
    if is_relevant:
        return (
            RelevanceBand.RELEVANT
            if score >= CONFIRMED_RELEVANCE_SCORE
            else RelevanceBand.UNCONFIRMED
        )
    return RelevanceBand.RELATED if score >= MIN_RELATED_SCORE else RelevanceBand.UNRELATED


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
