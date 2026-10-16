"""Logs estructurados en JSON (CLAUDE.md §6.1).

Cada línea de log es un objeto JSON con fecha UTC, nivel, origen, mensaje y
los campos extra que se pasen (por ejemplo ``search_id``). Así se pueden
filtrar y buscar con herramientas sin interpretar texto libre.

Lo usan la API y el worker al arrancar (``configure_logging``).
No hace: no envía logs a servicios externos; solo escribe a la salida estándar.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Atributos que trae todo LogRecord. Lo que no esté aquí es un campo "extra"
# que el código agregó a propósito y debe aparecer en el JSON.
_STANDARD_RECORD_ATTRS = frozenset(
    vars(logging.LogRecord("", logging.INFO, "", 0, "", None, None)).keys()
    | {"message", "asctime", "taskName"}
)


class JsonFormatter(logging.Formatter):
    """Convierte cada registro de log en una línea JSON.

    Example:
        >>> logger.info("Búsqueda iniciada", extra={"search_id": "abc"})
        {"timestamp": "2026-10-15T18:00:00.123456+00:00", "level": "INFO",
         "logger": "app.worker", "message": "Búsqueda iniciada", "search_id": "abc"}
    """

    def format(self, record: logging.LogRecord) -> str:
        """Arma la línea JSON del registro.

        Args:
            record: Registro de log de la biblioteca estándar.

        Returns:
            Una línea JSON con los campos estándar y los extra.
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # ensure_ascii=False conserva acentos y ñ legibles; default=str evita
        # que un valor no serializable (UUID, fecha) tumbe el log.
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    """Configura el logger raíz para escribir JSON a la salida estándar.

    Reemplaza los handlers existentes para que no haya líneas duplicadas
    (uvicorn y Celery instalan los suyos).

    Args:
        level: Nivel mínimo (``DEBUG``, ``INFO``, ``WARNING`` o ``ERROR``).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn trae handlers propios; se quitan para que todo pase por el JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
