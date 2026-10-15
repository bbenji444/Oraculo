"""Formato JSON de los logs."""

import json
import logging
import sys
import uuid

import pytest

from app.core.logging import JsonFormatter, configure_logging


def make_record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("app.prueba", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_produce_json_con_campos_basicos_y_fecha_utc() -> None:
    line = JsonFormatter().format(make_record("Búsqueda iniciada"))

    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.prueba"
    assert payload["message"] == "Búsqueda iniciada"
    assert payload["timestamp"].endswith("+00:00")


def test_incluye_campos_extra_como_search_id() -> None:
    search_id = uuid.uuid4()

    payload = json.loads(JsonFormatter().format(make_record("x", search_id=search_id)))

    assert payload["search_id"] == str(search_id)


def test_conserva_acentos_y_enie_legibles() -> None:
    line = JsonFormatter().format(make_record("Peñón de los Baños"))

    assert "Peñón de los Baños" in line


def test_incluye_la_excepcion() -> None:
    try:
        raise ValueError("falló")
    except ValueError:
        record = logging.LogRecord(
            "app", logging.ERROR, __file__, 1, "error", None, exc_info=sys.exc_info()
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: falló" in payload["exception"]


def test_configure_logging_deja_un_solo_handler_json(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    try:
        configure_logging("INFO")
        logging.getLogger("app.prueba").info("hola", extra={"search_id": "abc"})

        assert len(root.handlers) == 1
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert payload["search_id"] == "abc"
    finally:
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)
