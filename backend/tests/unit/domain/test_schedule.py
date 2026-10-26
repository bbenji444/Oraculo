"""Horarios de las corridas automáticas del monitor FGR (F12.8, ADR-0031)."""

from datetime import datetime

import pytest

from app.application.clock import MEXICO_CITY
from app.domain.errors import InvalidRequestError
from app.domain.schedule import parse_run_hours, run_slot, utc_hours

HOURS = (7, 15, 23)


def test_lee_los_horarios_de_benji_sin_importar_orden_ni_espacios() -> None:
    assert parse_run_hours("23, 7,15") == HOURS
    assert parse_run_hours("7,7,15") == (7, 15)


@pytest.mark.parametrize("value", ["", "siete", "7,24", "-1"])
def test_horarios_invalidos(value: str) -> None:
    with pytest.raises(InvalidRequestError):
        parse_run_hours(value)


@pytest.mark.parametrize(
    ("now", "slot"),
    [
        # El reloj la lanza a las 07:00:03: es la de las 07:00.
        (
            datetime(2026, 10, 26, 7, 0, 3, tzinfo=MEXICO_CITY),
            datetime(2026, 10, 26, 7, 0, tzinfo=MEXICO_CITY),
        ),
        # Arrancó tarde: sigue siendo la de las 07:00.
        (
            datetime(2026, 10, 26, 7, 40, tzinfo=MEXICO_CITY),
            datetime(2026, 10, 26, 7, 0, tzinfo=MEXICO_CITY),
        ),
        (
            datetime(2026, 10, 26, 15, 0, tzinfo=MEXICO_CITY),
            datetime(2026, 10, 26, 15, 0, tzinfo=MEXICO_CITY),
        ),
        (
            datetime(2026, 10, 26, 23, 59, tzinfo=MEXICO_CITY),
            datetime(2026, 10, 26, 23, 0, tzinfo=MEXICO_CITY),
        ),
        # De madrugada, antes de la primera: es la de las 23:00 de ayer.
        (
            datetime(2026, 10, 1, 3, 15, tzinfo=MEXICO_CITY),
            datetime(2026, 9, 30, 23, 0, tzinfo=MEXICO_CITY),
        ),
    ],
)
def test_a_que_corrida_pertenece_un_momento(now: datetime, slot: datetime) -> None:
    assert run_slot(now, HOURS) == slot


def test_las_horas_de_la_cdmx_en_utc() -> None:
    # CDMX = UTC-6 todo el año: 07:00 → 13:00, 15:00 → 21:00, 23:00 → 05:00.
    assert utc_hours(HOURS, -6) == (5, 13, 21)
