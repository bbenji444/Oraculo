"""Quién actúa en cada nota y la regla «FGR federal» (F12.5, ADR-0030)."""

import pytest

from app.domain.authority import (
    FGR_FEDERAL_EXCLUDED,
    LOW_CONFIDENCE_REASON,
    Authority,
    RelevanceRule,
    effective_relevance,
    parse_authority,
)

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
