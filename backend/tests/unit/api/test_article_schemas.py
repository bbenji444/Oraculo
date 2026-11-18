"""Esquema de los juicios de una nota: la banda de relevancia (ADR-0114)."""

import pytest

from app.api.v1.schemas.articles import JudgementOut
from app.application.ports.search_reads import JudgementView
from app.domain.concept import QueryMode


@pytest.mark.parametrize(
    ("is_relevant", "score", "band"),
    [
        (True, 0.92, "relevant"),
        (True, 0.7, "unconfirmed"),
        (False, 0.45, "related"),
        (False, 0.1, "unrelated"),
    ],
)
def test_cada_juicio_lleva_su_banda(is_relevant: bool, score: float, band: str) -> None:
    # Un concepto abierto (la búsqueda rápida): las cuatro bandas.
    view = JudgementView(9, "hacker eternal", is_relevant, score, "Razón.", QueryMode.OPEN)

    out = JudgementOut.from_view(view).model_dump(mode="json")

    assert out == {
        "concept_id": 9,
        "name": "hacker eternal",
        "is_relevant": is_relevant,
        "relevance_score": score,
        "relevance_reason": "Razón.",
        "relevance_band": band,
    }


@pytest.mark.parametrize(
    ("is_relevant", "score", "band"),
    [(True, 0.7, "relevant"), (False, 0.0, "related"), (False, 0.45, "related")],
)
def test_un_juicio_fgr_no_usa_las_bandas_de_los_abiertos(
    is_relevant: bool, score: float, band: str
) -> None:
    # Revisión del 18/11/2026: un «no» de la FGR con 0 salía «unrelated» y la
    # pantalla no lo mostraba ni con «Incluir las no relevantes».
    view = JudgementView(13, "FGR", is_relevant, score, "Razón.", QueryMode.EXACT)

    assert JudgementOut.from_view(view).relevance_band == band


def test_la_banda_esta_en_el_esquema_publicado() -> None:
    schema = JudgementOut.model_json_schema()

    assert "relevance_band" in schema["required"]
    assert set(schema["$defs"]["RelevanceBand"]["enum"]) == {
        "relevant",
        "unconfirmed",
        "related",
        "unrelated",
    }
