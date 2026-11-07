"""Tareas periódicas y programación del reloj de Celery (sin red ni base)."""

import logging
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from celery.schedules import crontab

from app.application.clock import MEXICO_CITY
from app.application.use_cases.ingest import IngestReport, PurgeReport
from app.application.use_cases.run_search import SearchReport
from app.core.config import Settings
from app.domain.search import SearchStatus
from app.worker import tasks
from app.worker.automatic_jobs import automatic_settings, report_file_name
from app.worker.celery_app import (
    AUTOMATIC_RUN_TASK,
    SCHEDULE_TICK_TASK,
    build_beat_schedule,
    celery_app,
)
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


def test_el_reloj_revisa_el_horario_unico_cada_minuto() -> None:
    # ADR-0040: el horario vive en la base y se edita desde «Envíos»; el reloj
    # revisa cada minuto si toca una corrida, sin reiniciarse al cambiarlo.
    monitor = build_beat_schedule(Settings())["monitor-fgr"]

    assert monitor["task"] == SCHEDULE_TICK_TASK
    assert monitor["schedule"] == 60.0
    assert monitor["options"] == {"expires": 60}


def test_el_monitor_se_apaga_desde_la_configuracion() -> None:
    assert "monitor-fgr" not in build_beat_schedule(Settings(automatic_runs_enabled=False))


def test_las_corridas_automaticas_tienen_su_propio_tope_para_la_ia() -> None:
    general = Settings(llm_max_articles_per_search=150)
    assert automatic_settings(general).llm_max_articles_per_search == 250
    # Las búsquedas manuales no cambian.
    assert general.llm_max_articles_per_search == 150
    propio = Settings(llm_max_articles_per_search=150, automatic_llm_max_articles=300)
    assert automatic_settings(propio).llm_max_articles_per_search == 300


def test_el_pdf_de_cada_corrida_se_nombra_por_fecha_y_hora() -> None:
    assert (
        report_file_name(datetime(2026, 10, 26, 7, 0, tzinfo=MEXICO_CITY))
        == "fgr_2026-10-26_0700.pdf"
    )


def test_las_tareas_estan_registradas_con_su_nombre() -> None:
    assert {
        tasks.INGEST_TASK,
        tasks.PURGE_TASK,
        tasks.SEARCH_TASK,
        AUTOMATIC_RUN_TASK,
        SCHEDULE_TICK_TASK,
    } <= set(celery_app.tasks)
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

    async def fake_texts(settings: Settings) -> int:
        return 7

    monkeypatch.setattr(tasks, "run_purge", fake_purge)
    monkeypatch.setattr(tasks, "purge_article_texts", fake_texts)

    assert tasks.purge_news_index() == {"deleted": 42, "bodies_cleared": 5, "texts_deleted": 7}


def test_la_busqueda_corre_y_devuelve_su_resumen(monkeypatch: pytest.MonkeyPatch) -> None:
    search_id = uuid4()

    async def fake_job(settings: Settings, wanted: UUID) -> SearchReport:
        assert wanted == search_id
        return SearchReport(
            search_id, SearchStatus.PARTIAL, articles=12, credits_used=1, llm_cost_usd=0.00412
        )

    monkeypatch.setattr(tasks, "run_search_job", fake_job)

    assert tasks.run_search(str(search_id)) == {
        "status": "partial",
        "articles": 12,
        "credits_used": 1,
        "llm_cost_usd": 0.0041,
    }
