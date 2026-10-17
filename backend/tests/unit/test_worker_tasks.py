"""Tareas periódicas y programación del reloj de Celery (sin red ni base)."""

import logging

import pytest
from celery.schedules import crontab

from app.application.use_cases.ingest import IngestReport, PurgeReport
from app.core.config import Settings
from app.worker import tasks
from app.worker.celery_app import build_beat_schedule, celery_app
from app.worker.ingest_jobs import IngestSummary
from tests.unit.fake_ingest import FILE


def test_el_reloj_programa_la_ingesta_y_la_limpieza() -> None:
    schedule = build_beat_schedule(Settings(ingest_interval_minutes=15))

    ingest = schedule["ingesta-indice-local"]
    assert (ingest["task"], ingest["schedule"]) == (tasks.INGEST_TASK, 900.0)
    # Una corrida atrasada se descarta antes de que llegue la siguiente.
    assert ingest["options"] == {"expires": 900}
    purge = schedule["limpieza-indice-local"]
    assert purge["task"] == tasks.PURGE_TASK
    assert purge["schedule"] == crontab(hour=9, minute=30)


def test_las_tareas_estan_registradas_con_su_nombre() -> None:
    assert {tasks.INGEST_TASK, tasks.PURGE_TASK} <= set(celery_app.tasks)
    assert "ingesta-indice-local" in celery_app.conf.beat_schedule


def test_la_ingesta_registra_cada_fuente_y_devuelve_las_nuevas(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    gdelt = IngestReport("gdelt_gkg", FILE.name, "ok", items_new=120)
    broken = IngestReport("rss:roto", "https://roto.example/rss", "error", message="No es un RSS")

    async def fake_ingest(settings: Settings) -> IngestSummary:
        return IngestSummary(gdelt=gdelt, media=[broken])

    monkeypatch.setattr(tasks, "run_ingest", fake_ingest)

    with caplog.at_level(logging.INFO):
        result = tasks.ingest_news()

    assert result == {"gdelt_gkg": 120, "rss:roto": 0}
    assert "Ingesta terminada" in caplog.text
    assert "Ingesta con error: No es un RSS" in caplog.text


def test_la_limpieza_devuelve_cuantas_borro(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_purge(settings: Settings) -> PurgeReport:
        return PurgeReport(notes_deleted=42, bodies_cleared=5)

    monkeypatch.setattr(tasks, "run_purge", fake_purge)

    assert tasks.purge_news_index() == {"deleted": 42, "bodies_cleared": 5}
