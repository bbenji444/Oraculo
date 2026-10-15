"""Creación de la app de Celery compartida por el worker y la API.

El worker se arranca con ``celery -A app.worker.celery_app worker`` (lo hace
``make up``). La API usa la misma configuración para encolar tareas y para
el revisor de salud del worker.

No hace: en F0 todavía no define tareas; el pipeline de búsqueda llega en F4.
"""

from celery import Celery

from app.core.config import Settings, get_settings


def create_celery_app(settings: Settings) -> Celery:
    """Crea una app de Celery conectada al Redis configurado.

    Args:
        settings: Configuración con ``redis_url``.

    Returns:
        La app de Celery lista para encolar tareas o arrancar un worker.
    """
    app = Celery("monitor_noticias", broker=settings.redis_url)
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
    )
    return app


# Instancia que busca la línea de comandos de Celery (`-A app.worker.celery_app`).
celery_app = create_celery_app(get_settings())
