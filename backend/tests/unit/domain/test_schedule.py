"""Horarios de las corridas automáticas del monitor FGR (F12.8, ADR-0031)."""

from datetime import datetime, timedelta

import pytest

from app.application.clock import MEXICO_CITY
from app.domain.errors import InvalidRequestError
from app.domain.schedule import (
    RunWindow,
    parse_run_hours,
    previous_slot,
    run_slot,
    run_window,
    utc_hours,
)

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


HOURS = (7, 15, 23)
DAY = timedelta(days=1)


def cdmx(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=MEXICO_CITY)


@pytest.mark.parametrize(
    ("slot", "start"),
    [
        # La de las 07:00 cubre la noche: desde las 23:00 de ayer (Benji, 28/10/2026).
        (cdmx(28, 7), cdmx(27, 23)),
        (cdmx(28, 15), cdmx(28, 7)),
        (cdmx(28, 23), cdmx(28, 15)),
    ],
)
def test_cada_corrida_cubre_solo_desde_la_anterior(slot: datetime, start: datetime) -> None:
    assert previous_slot(slot, HOURS) == start
    assert run_window(slot, HOURS, start, DAY) == RunWindow(start, slot)


def test_si_la_anterior_fallo_cubre_desde_la_ultima_que_termino() -> None:
    # La de las 15:00 no terminó: la de las 23:00 cubre desde las 07:00.
    window = run_window(cdmx(28, 23), HOURS, cdmx(28, 7), DAY)
    assert window.start == cdmx(28, 7)


def test_nunca_mira_mas_atras_del_tope() -> None:
    # El servidor estuvo apagado tres días: se mira solo un día hacia atrás.
    window = run_window(cdmx(28, 15), HOURS, cdmx(25, 7), DAY)
    assert window.start == cdmx(27, 15)
    # Sin ninguna corrida terminada, desde la programada anterior.
    assert run_window(cdmx(28, 15), HOURS, None, DAY).start == cdmx(28, 7)


def test_el_margen_es_opcional() -> None:
    window = run_window(cdmx(28, 15), HOURS, cdmx(28, 7), DAY, timedelta(minutes=30))
    assert window.start == cdmx(28, 6, 30)


def test_que_notas_le_tocan_a_la_ventana() -> None:
    window = RunWindow(cdmx(27, 23), cdmx(28, 7))
    assert window.contains(cdmx(27, 23))
    assert window.contains(cdmx(28, 6, 59))
    # Lo publicado justo a las 07:00 es de la corrida siguiente.
    assert not window.contains(cdmx(28, 7))
    assert not window.contains(cdmx(27, 22, 59))
    # Sin fecha no se puede saber si ya salió: no le toca.
    assert not window.contains(None)
