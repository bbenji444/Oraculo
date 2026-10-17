"""Comando ``make ngramas-muestra``: opciones y ejemplos (sin red ni base)."""

import logging

import pytest

from app.application.use_cases.ingest import IngestReport
from app.cli import muestra_ngramas
from app.domain.news_index import NewsItem
from tests.unit.fake_ingest import NOW


def test_los_minutos_deben_ser_positivos() -> None:
    with pytest.raises(SystemExit) as exit_info:
        muestra_ngramas.main(["--minutos", "0"])

    assert exit_info.value.code == 2


def test_los_ejemplos_dicen_medio_fecha_y_frases(caplog: pytest.LogCaptureFixture) -> None:
    item = NewsItem.create(
        source="gdelt_ngrams",
        url="https://www.proceso.com.mx/nota",
        title="Detienen a dos mujeres en la Del Valle",
        published_at=NOW,
        body_phrases=["en la Del Valle", "la colonia Del Valle"],
    )
    report = IngestReport("gdelt_ngrams", "20261016223100.toc.json.gz", "ok", sample=(item,))

    with caplog.at_level(logging.INFO):
        muestra_ngramas._show_examples([report])

    assert "1 ejemplos reales" in caplog.text
    assert "1. Detienen a dos mujeres en la Del Valle" in caplog.text
    assert "proceso.com.mx · 16/10/2026 14:00 · 2 frases del cuerpo" in caplog.text
