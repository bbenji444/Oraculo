"""Revisores de salud contra servicios reales (base de pruebas y Redis de pruebas)."""

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.health.celery_probe import CeleryWorkerHealthProbe
from app.adapters.health.postgres_probe import REQUIRED_EXTENSIONS, PostgresHealthProbe
from app.adapters.health.redis_probe import RedisHealthProbe
from app.core.config import Settings
from app.domain.health import ComponentStatus
from app.worker.celery_app import create_celery_app

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_postgres_reporta_version_16_y_extensiones(test_engine: AsyncEngine) -> None:
    result = await PostgresHealthProbe(test_engine).check()

    assert result.status is ComponentStatus.OK, result.detail
    assert result.info["postgres"].startswith("16.")
    assert set(REQUIRED_EXTENSIONS) <= set(result.info)


async def test_unaccent_convierte_la_enie_y_name_norm_debe_protegerla(
    test_engine: AsyncEngine,
) -> None:
    # Hallazgo para F1 (CLAUDE.md §6.3 exige conservar la Ñ en name_norm):
    # unaccent de PostgreSQL convierte la ñ en n. Si esta prueba deja de
    # pasar, cambió el diccionario de unaccent y hay que revisar name_norm.
    async with test_engine.connect() as conn:
        unaccented = (await conn.execute(text("SELECT unaccent('Peñón')"))).scalar_one()

    assert unaccented == "Penon"


async def test_redis_responde_con_su_version(test_redis: Redis) -> None:
    result = await RedisHealthProbe(test_redis).check()

    assert result.status is ComponentStatus.OK, result.detail
    assert result.info["version"]


async def test_worker_sin_workers_en_el_redis_de_pruebas_es_error(settings: Settings) -> None:
    # En la base 15 de Redis no escucha ningún worker: el revisor debe decirlo.
    celery_app = create_celery_app(
        settings.model_copy(update={"redis_url": settings.redis_test_url})
    )

    result = await CeleryWorkerHealthProbe(celery_app, reply_timeout_seconds=0.3).check()

    assert result.status is ComponentStatus.ERROR
    assert result.detail is not None
    assert "Ningún worker respondió" in result.detail
