"""Creación de la app de Celery compartida por el worker, el reloj y la API.

El worker se arranca con ``celery -A app.worker.celery_app worker`` y el
reloj con ``celery -A app.worker.celery_app beat`` (los dos los arranca
``make up``). La API usa la misma configuración para encolar tareas y para
el revisor de salud del worker.

El reloj (``beat_schedule``) dispara la ingesta al índice local cada
``INGEST_INTERVAL_MINUTES``, la limpieza por retención una vez al día
(ADR-0013) y las corridas automáticas del monitor FGR a las 07:00, 15:00 y
23:00 de la Ciudad de México (``AUTOMATIC_RUN_HOURS``, F12.8, ADR-0031). Las
tareas están en ``app.worker.tasks``.

No hace: no contiene lógica de las tareas.
"""

from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.domain.schedule import parse_run_hours, utc_hours

_SECONDS_PER_MINUTE = 60
# Limpieza diaria a las 09:30 UTC = 03:30 en la Ciudad de México: de madrugada,
# lejos de las horas de uso.
_PURGE_HOUR_UTC = 9
_PURGE_MINUTE = 30
AUTOMATIC_RUN_TASK = "monitor.automatic_run"
# La Ciudad de México está en UTC-6 todo el año desde que se quitó el horario
# de verano (octubre de 2022). Si volviera, basta reiniciar el reloj con el
# nuevo desfase.
_MEXICO_CITY_UTC_OFFSET = -6
# Una corrida que no alcanzó a empezar en 2 horas se descarta: la siguiente
# (8 horas después) cubre hoy y ayer, así que no se pierde nada.
_AUTOMATIC_RUN_EXPIRES_SECONDS = 2 * 60 * 60


def build_beat_schedule(settings: Settings) -> dict[str, dict[str, Any]]:
    """Programación del reloj de Celery.

    Args:
        settings: Configuración con ``ingest_interval_minutes``.

    Returns:
        El ``beat_schedule`` de Celery. Una ingesta que no alcanzó a correr
        antes de la siguiente se descarta (``expires``): así nunca se juntan
        dos corridas atrasadas sobre el mismo archivo.
    """
    interval_seconds = settings.ingest_interval_minutes * _SECONDS_PER_MINUTE
    schedule: dict[str, dict[str, Any]] = {
        "ingesta-indice-local": {
            "task": "ingest.news",
            "schedule": float(interval_seconds),
            "options": {"expires": interval_seconds},
        },
        "limpieza-indice-local": {
            "task": "ingest.purge",
            "schedule": crontab(hour=_PURGE_HOUR_UTC, minute=_PURGE_MINUTE),
        },
    }
    if settings.automatic_runs_enabled:
        hours = utc_hours(parse_run_hours(settings.automatic_run_hours), _MEXICO_CITY_UTC_OFFSET)
        schedule["monitor-fgr"] = {
            "task": AUTOMATIC_RUN_TASK,
            "schedule": crontab(hour=",".join(str(h) for h in hours), minute=0),
            "options": {"expires": _AUTOMATIC_RUN_EXPIRES_SECONDS},
        }
    return schedule


def create_celery_app(settings: Settings) -> Celery:
    """Crea una app de Celery conectada al Redis configurado.

    Args:
        settings: Configuración con ``redis_url``.

    Returns:
        La app de Celery lista para encolar tareas o arrancar un worker.
    """
    app = Celery("monitor_noticias", broker=settings.redis_url, include=["app.worker.tasks"])
    app.conf.update(
        # JSON y no pickle: los mensajes no pueden ejecutar código al leerse.
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        # Fechas en UTC (CLAUDE.md §6.3).
        timezone="UTC",
        enable_utc=True,
        # Reintenta la conexión al broker al arrancar en lugar de morir si
        # Redis tarda un poco en estar listo.
        broker_connection_retry_on_startup=True,
        # El worker no debe tomar los logs de la app por su cuenta: usamos
        # el formato JSON de app.core.logging.
        worker_hijack_root_logger=False,
        beat_schedule=build_beat_schedule(settings),
    )
    return app


@setup_logging.connect
def _use_json_logs(**_: Any) -> None:
    """Logs del worker y del reloj en JSON, como la API (CLAUDE.md §6.1).

    Conectarse a esta señal le dice a Celery que no configure sus propios
    logs. Sin esto, el worker escribía con el formato de texto de Celery y,
    como el logger raíz quedaba sin configurar, los mensajes INFO de las
    tareas no tenían por dónde salir.
    """
    configure_logging(get_settings().log_level)


# Instancia que busca la línea de comandos de Celery (`-A app.worker.celery_app`).
celery_app = create_celery_app(get_settings())
