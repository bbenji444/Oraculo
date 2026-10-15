"""Salida legible para los comandos del pipeline de geodatos.

Los servicios (API, worker) escriben logs JSON para máquinas
(``app.core.logging``). Estos comandos los corre una persona en la terminal,
así que el mismo ``logging`` se configura con un formato legible: títulos de
paso, marcas de "listo" y avisos. Así no se usa ``print`` (CLAUDE.md §6.1).

No hace: no guarda logs en archivo.
"""

import logging
import sys

# Atributo extra que marca un mensaje como título de paso.
HEADING = "heading"


class _ConsoleFormatter(logging.Formatter):
    """Da formato de terminal: '==> título', '    ✔ listo', '    ! aviso'."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if getattr(record, HEADING, False):
            return f"\n==> {message}"
        if record.levelno >= logging.ERROR:
            return f"\n✘ {message}"
        if record.levelno >= logging.WARNING:
            return f"    ! {message}"
        return f"    ✔ {message}"


def configure_cli_logging() -> None:
    """Configura el logger raíz para mostrar mensajes legibles en la terminal."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ConsoleFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def heading(logger: logging.Logger, message: str) -> None:
    """Escribe un título de paso.

    Args:
        logger: Logger del módulo que llama.
        message: Título, en español.
    """
    logger.info(message, extra={HEADING: True})
