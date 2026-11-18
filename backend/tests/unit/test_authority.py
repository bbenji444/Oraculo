"""Quién actúa en cada nota y la regla «FGR federal» (F12.5, ADR-0030)."""

import pytest

from app.domain.authority import (
    CONFIRMED_RELEVANCE_SCORE,
    FGR_FEDERAL_EXCLUDED,
    LOW_CONFIDENCE_REASON,
    MIN_RELATED_SCORE,
    MIN_RELEVANCE_SCORE,
    Authority,
    RelevanceBand,
    RelevanceRule,
    effective_relevance,
    parse_authority,
    relevance_band,
)
from app.domain.concept import QueryMode

AI_REASON = "La nota menciona a la FGR."


@pytest.mark.parametrize("authority", [Authority.FGR_MENTION, Authority.STATE, Authority.OTHER])
def test_fgr_federal_deja_fuera_si_no_actua_la_fgr(authority: Authority) -> None:
    relevant, reason = effective_relevance(True, AI_REASON, RelevanceRule.FGR_FEDERAL, authority)

    assert relevant is False
    assert reason == FGR_FEDERAL_EXCLUDED[authority]


def test_fosa_de_slp_actua_la_fiscalia_estatal() -> None:
    # Nota 1382 del 24/10/2026: la IA la marcó relevante (0.75) por dos oficios de la FGR.
    assert effective_relevance(True, AI_REASON, RelevanceRule.FGR_FEDERAL, Authority.STATE) == (
        False,
        "Actúa una fiscalía estatal, no la FGR.",
    )


@pytest.mark.parametrize("authority", [Authority.FGR, Authority.UNKNOWN, None])
@pytest.mark.parametrize("ai_relevant", [True, False])
def test_fgr_federal_respeta_a_la_ia_si_actua_la_fgr_o_no_se_sabe(
    authority: Authority | None, ai_relevant: bool
) -> None:
    assert effective_relevance(ai_relevant, AI_REASON, RelevanceRule.FGR_FEDERAL, authority) == (
        ai_relevant,
        AI_REASON,
    )


@pytest.mark.parametrize("authority", [*Authority, None])
def test_la_regla_general_nunca_cambia_la_relevancia(authority: Authority | None) -> None:
    assert effective_relevance(True, AI_REASON, RelevanceRule.GENERAL, authority) == (
        True,
        AI_REASON,
    )


def test_una_regla_no_convierte_en_relevante_lo_que_la_ia_descarto() -> None:
    assert effective_relevance(False, "No trata de la FGR.", RelevanceRule.FGR_FEDERAL, None) == (
        False,
        "No trata de la FGR.",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("estatal", Authority.STATE),
        (" FGR ", Authority.FGR),
        ("fgr_mencion", Authority.FGR_MENTION),
        ("policía", Authority.UNKNOWN),
        (None, None),
    ],
)
def test_lee_quien_actua(raw: str | None, expected: Authority | None) -> None:
    assert parse_authority(raw) == expected


def test_un_si_con_poca_confianza_no_cuenta() -> None:
    # 11/11/2026: «sé mucho más estricto». Por debajo de 0.6 la IA misma dice
    # que el tema es secundario o dudoso.
    low = effective_relevance(True, "Lo menciona", RelevanceRule.GENERAL, None, 0.35)
    high = effective_relevance(True, "Es el asunto principal", RelevanceRule.GENERAL, None, 0.8)
    edge = effective_relevance(True, "Justo en el límite", RelevanceRule.GENERAL, None, 0.6)
    unknown = effective_relevance(True, "Sin puntaje", RelevanceRule.GENERAL, None)

    assert low == (False, LOW_CONFIDENCE_REASON)
    assert high == (True, "Es el asunto principal")
    assert edge[0] is True
    assert unknown[0] is True


def test_un_no_sigue_siendo_no_aunque_tenga_puntaje() -> None:
    assert effective_relevance(False, "No trata", RelevanceRule.GENERAL, None, 0.9)[0] is False


@pytest.mark.parametrize(
    ("is_relevant", "score", "band"),
    [
        (True, 1.0, RelevanceBand.RELEVANT),
        (True, CONFIRMED_RELEVANCE_SCORE, RelevanceBand.RELEVANT),
        (True, 0.79, RelevanceBand.UNCONFIRMED),
        (True, MIN_RELEVANCE_SCORE, RelevanceBand.UNCONFIRMED),
        (False, 0.59, RelevanceBand.RELATED),
        (False, MIN_RELATED_SCORE, RelevanceBand.RELATED),
        (False, 0.29, RelevanceBand.UNRELATED),
        (False, 0.0, RelevanceBand.UNRELATED),
    ],
)
def test_bandas_de_puntaje(is_relevant: bool, score: float, band: RelevanceBand) -> None:
    # ADR-0114: relevante ≥0.8, por confirmar 0.6–0.79, cercana 0.3–0.59, ajena <0.3,
    # en los conceptos abiertos (las bandas solo las pide su prompt).
    assert relevance_band(is_relevant, score, QueryMode.OPEN) is band


def test_la_banda_sale_de_la_relevancia_final() -> None:
    # La regla FGR federal deja fuera una nota que la IA puntuó 0.9: ya no es
    # relevante, pero sí del tema (cercana), no ajena.
    relevant, _reason = effective_relevance(
        True, AI_REASON, RelevanceRule.FGR_FEDERAL, Authority.STATE, 0.9
    )

    assert relevance_band(relevant, 0.9, QueryMode.EXACT) is RelevanceBand.RELATED
    # Un «sí» con poca confianza baja a no relevante: cercana o ajena por su puntaje.
    low, _ = effective_relevance(True, AI_REASON, RelevanceRule.GENERAL, None, 0.45)
    assert relevance_band(low, 0.45, QueryMode.OPEN) is RelevanceBand.RELATED


def test_los_umbrales_de_las_bandas() -> None:
    assert (MIN_RELATED_SCORE, MIN_RELEVANCE_SCORE, CONFIRMED_RELEVANCE_SCORE) == (0.3, 0.6, 0.8)


# --- La banda según el modo del concepto (revisión del 18/11/2026, hallazgo 1) ---


def test_un_juicio_fgr_de_score_0_es_cercano_y_se_ve_con_el_interruptor() -> None:
    # «Confirma Fiscalía orden de aprehensión contra Vadhir» (concepto 13 de la
    # base de desarrollo) tiene 0: con las bandas de los abiertos salía
    # «unrelated» y la pantalla nunca la mostraba, ni con «Incluir las no
    # relevantes». En un concepto exacto toda no relevante es «related».
    assert relevance_band(False, 0.0, QueryMode.EXACT) is RelevanceBand.RELATED
    assert relevance_band(False, 0.45, QueryMode.EXACT) is RelevanceBand.RELATED


@pytest.mark.parametrize("score", [MIN_RELEVANCE_SCORE, 0.7, 0.79, CONFIRMED_RELEVANCE_SCORE, 1.0])
def test_un_relevante_fgr_nunca_queda_por_confirmar(score: float) -> None:
    # El prompt de los exactos (texto de v5) no define bandas: «por confirmar»
    # sería una marca que la IA nunca quiso poner.
    assert relevance_band(True, score, QueryMode.EXACT) is RelevanceBand.RELEVANT


def test_un_concepto_abierto_sigue_con_las_cuatro_bandas() -> None:
    assert relevance_band(True, 0.7, QueryMode.OPEN) is RelevanceBand.UNCONFIRMED
    assert relevance_band(False, 0.1, QueryMode.OPEN) is RelevanceBand.UNRELATED
