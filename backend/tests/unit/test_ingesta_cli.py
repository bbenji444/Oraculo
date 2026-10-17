"""Comando ``make ingesta`` con la ingesta simulada (sin red ni base)."""

import logging
from collections.abc import Awaitable, Callable

import pytest

from app.application.use_cases.ingest import IngestReport
from app.cli import ingesta
from app.core.config import Settings
from app.worker.ingest_jobs import IngestSummary
from tests.unit.fake_ingest import FILE, news

pytestmark = pytest.mark.anyio


def fake_run(summary: IngestSummary) -> Callable[[Settings], Awaitable[IngestSummary]]:
    async def run_ingest(settings: Settings) -> IngestSummary:
        return summary

    return run_ingest


async def test_muestra_numeros_y_ejemplos(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    report = IngestReport(
        "gdelt_gkg", FILE.name, "ok", 2, 2, 50, 8_000_000, sample=(news(1), news(2))
    )
    monkeypatch.setattr(ingesta, "run_ingest", fake_run(IngestSummary(gdelt=report)))

    with caplog.at_level(logging.INFO):
        code = await ingesta.run()

    assert code == 0
    assert "50 leídas · 2 válidas · 2 nuevas" in caplog.text
    assert "1. Nota 1" in caplog.text
    assert "https://medio.mx/nota-2" in caplog.text


async def test_una_fuente_con_error_devuelve_1(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    failed = IngestReport("rss:roto", "https://roto.example/rss", "error", message="No es un RSS")
    skipped = IngestReport("gdelt_gkg", FILE.name, "skipped", message="Ya procesado.")
    monkeypatch.setattr(
        ingesta, "run_ingest", fake_run(IngestSummary(gdelt=skipped, media=[failed]))
    )

    with caplog.at_level(logging.INFO):
        code = await ingesta.run()

    assert code == 1
    assert "Sin novedades: Ya procesado." in caplog.text
    assert "Falló: No es un RSS" in caplog.text
