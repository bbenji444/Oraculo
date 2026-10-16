"""Comando ``make ingesta-historial``: opciones y textos (sin red ni base)."""

import logging

import pytest

from app.application.use_cases.ingest import HistoryPlan
from app.cli import ingesta_historial
from tests.unit.fake_ingest import FILE


@pytest.mark.parametrize("days", ["0", "91"])
def test_los_dias_deben_caber_en_la_retencion(days: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        ingesta_historial.main(["--dias", days])

    assert exit_info.value.code == 2


def test_la_vista_previa_dice_cuanto_y_cuanto_tarda(caplog: pytest.LogCaptureFixture) -> None:
    plan = HistoryPlan((FILE, FILE), already_done=3, missing=1, failed=("x: sin MD5",))

    with caplog.at_level(logging.INFO):
        ingesta_historial._show_plan(plan, total=7)
        ingesta_historial._progress(96, 672)
        ingesta_historial._progress(5, 672)

    assert "7 cuartos de hora · 3 ya en el índice · 1 sin archivo en GDELT" in caplog.text
    assert "Pendientes: 2 archivos" in caplog.text
    assert "x: sin MD5" in caplog.text
    assert "Revisados 96 de 672" in caplog.text
    assert "Revisados 5 de" not in caplog.text
