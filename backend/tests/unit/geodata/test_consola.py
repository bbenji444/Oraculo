"""Formato legible de la salida de los comandos de geodatos."""

import logging

import pytest

from app.geodata.consola import configure_cli_logging, heading


@pytest.fixture
def restore_root_logger() -> object:
    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    yield None
    root.handlers[:] = previous_handlers
    root.setLevel(previous_level)


def test_formatos_de_titulo_listo_aviso_y_error(
    restore_root_logger: object, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_cli_logging()
    logger = logging.getLogger("app.geodata.prueba")

    heading(logger, "Descargando INEGI")
    logger.info("Peñón listo")
    logger.warning("Archivo grande")
    logger.error("Falló")

    assert capsys.readouterr().out.splitlines() == [
        "",
        "==> Descargando INEGI",
        "    ✔ Peñón listo",
        "    ! Archivo grande",
        "",
        "✘ Falló",
    ]
