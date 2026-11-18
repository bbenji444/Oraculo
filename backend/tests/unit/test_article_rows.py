"""Cómo se arma un juicio leído de la base (``article_rows.judgement_view``).

Lo que se cuida aquí es la banda de relevancia según el modo del concepto
(ADR-0114, revisión del 18/11/2026): el monitor FGR (exacto) no usa las
bandas de los conceptos abiertos.
"""

from app.adapters.persistence.article_rows import judgement_view
from app.domain.authority import Authority, RelevanceBand, RelevanceRule
from app.domain.concept import QueryMode

# Concepto 13 de la base de desarrollo (FGR, exacto), nota real con 0.
VADHIR = "Confirma Fiscalía orden de aprehensión contra Vadhir"


def test_un_juicio_fgr_de_score_0_queda_cercano() -> None:
    row = [13, "FGR", False, 0.0, VADHIR, RelevanceRule.FGR_FEDERAL.value, "exact"]

    view = judgement_view(row, Authority.FGR)

    assert view.query_mode is QueryMode.EXACT
    assert view.band is RelevanceBand.RELATED


def test_un_relevante_fgr_de_0_7_no_queda_por_confirmar() -> None:
    row = [13, "FGR", True, 0.7, "Catea la FGR.", RelevanceRule.FGR_FEDERAL.value, "exact"]

    assert judgement_view(row, Authority.FGR).band is RelevanceBand.RELEVANT


def test_un_juicio_abierto_usa_las_cuatro_bandas() -> None:
    row = [9, "hacker eternal", False, 0.1, "Otra cosa.", RelevanceRule.GENERAL.value, "open"]

    view = judgement_view(row, None)

    assert view.query_mode is QueryMode.OPEN
    assert view.band is RelevanceBand.UNRELATED
