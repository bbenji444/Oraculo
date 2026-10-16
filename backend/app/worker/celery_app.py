"""Creación de la app de Celery compartida por el worker, el reloj y la API.

El worker se arranca con ``celery -A app.worker.celery_app worker`` y el
reloj con ``celery -A app.worker.celery_app beat`` (los dos los arranca
``make up``). La API usa la misma configuración para encolar tareas y para
el revisor de salud del worker.

El reloj (``beat_schedule``) dispara la ingesta al índice local cada
``INGEST_INTERVAL_MINUTES`` y la limpieza por retención una vez al día
(ADR-0013). Las tareas están en ``app.worker.tasks``.

No hace: no contiene lógica de las tareas.
"""

from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging

_SECONDS_PER_MINUTE = 60
# Limpieza diaria a las 09:30 UTC = 03:30 en la Ciudad de México: de madrugada,
# lejos de las horas de uso.
_PURGE_HOUR_UTC = 9
_PURGE_MINUTE = 30


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
    return {
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
