"""Horario único de las corridas automáticas del monitor FGR (ADR-0031, ADR-0040)."""

from datetime import datetime, timedelta
from typing import cast

import pytest

from app.application.clock import MEXICO_CITY
from app.domain.errors import InvalidRequestError, ScheduleValidationError
from app.domain.schedule import (
    RunSchedule,
    RunWindow,
    format_time,
    parse_run_hours,
    parse_time,
)

BENJI = RunSchedule.from_hours((7, 15, 23))


def cdmx(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, second, tzinfo=MEXICO_CITY)


def test_lee_las_horas_iniciales_sin_importar_orden_ni_espacios() -> None:
    assert parse_run_hours("23, 7,15") == (7, 15, 23)
    assert parse_run_hours("7,7,15") == (7, 15)
    assert BENJI.times == (420, 900, 1380)


@pytest.mark.parametrize("value", ["", "siete", "7,24", "-1"])
def test_horas_iniciales_invalidas(value: str) -> None:
    with pytest.raises(InvalidRequestError):
        parse_run_hours(value)


def test_horas_como_texto() -> None:
    assert parse_time("9:30") == 570
    assert parse_time(" 23:59 ") == 1439
    assert format_time(570) == "09:30"
    for bad in ("24:00", "09:60", "nueve", "9"):
        with pytest.raises(ScheduleValidationError):
            parse_time(bad)


def test_un_horario_valido_se_ordena_y_siete_dias_son_todos() -> None:
    schedule = RunSchedule.validated((1380, 420, 900, 420), (5, 1, 5))
    assert (schedule.times, schedule.days) == ((420, 900, 1380), (1, 5))
    assert RunSchedule.validated((420,), (1, 2, 3, 4, 5, 6, 7)).days == ()


@pytest.mark.parametrize(
    ("times", "days", "message"),
    [
        ((), (), "al menos una hora"),
        ((1440,), (), "entre 00:00 y 23:59"),
        (tuple(range(0, 1440, 160)), (), "Máximo 8"),
        ((420, 450), (), "al menos 60 minutos"),
        # La última y la primera del día siguiente también cuentan.
        ((10, 1410), (), "al menos 60 minutos"),
        ((420,), (8,), "1 \\(lunes\\)"),
    ],
)
def test_topes_del_horario(times: tuple[int, ...], days: tuple[int, ...], message: str) -> None:
    with pytest.raises(ScheduleValidationError, match=message) as error:
        RunSchedule.validated(times, days)
    problems = cast(list[dict[str, str]], error.value.details["problemas"])
    assert problems[0]["campo"] in {"times", "days"}


def test_ocho_horas_separadas_una_hora_si_caben() -> None:
    assert len(RunSchedule.validated(tuple(range(0, 1440, 180))).times) == 8


@pytest.mark.parametrize(
    ("now", "slot"),
    [
        # El reloj la ve a las 07:00:30: es la de las 07:00.
        (cdmx(26, 7, 0, 30), cdmx(26, 7)),
        # Arrancó tarde: sigue siendo la de las 07:00.
        (cdmx(26, 7, 40), cdmx(26, 7)),
        (cdmx(26, 23, 59), cdmx(26, 23)),
        # De madrugada, antes de la primera: es la de las 23:00 de ayer.
        (cdmx(1, 3, 15), datetime(2026, 9, 30, 23, tzinfo=MEXICO_CITY)),
    ],
)
def test_a_que_corrida_pertenece_un_momento(now: datetime, slot: datetime) -> None:
    assert BENJI.slot_at_or_before(now) == slot


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
    assert BENJI.previous(slot) == start
    assert BENJI.window(slot) == RunWindow(start, slot)


def test_una_hora_nueva_cubre_desde_la_anterior_y_acorta_la_siguiente() -> None:
    # Benji, 06/11/2026: con las 19:00 agregadas, esa corrida va de 15:00 a 19:00
    # y la de las 23:00 de 19:00 a 23:00. Ninguna nota se repite ni se pierde.
    schedule = RunSchedule.validated((420, 900, 1140, 1380))
    assert schedule.window(cdmx(28, 19)) == RunWindow(cdmx(28, 15), cdmx(28, 19))
    assert schedule.window(cdmx(28, 23)) == RunWindow(cdmx(28, 19), cdmx(28, 23))


def test_con_dias_la_primera_de_la_semana_cubre_desde_la_ultima_corrida() -> None:
    weekdays = RunSchedule.validated((420, 1380), (1, 2, 3, 4, 5))
    monday = cdmx(26, 7)  # 26/10/2026 es lunes
    friday_night = cdmx(23, 23)
    assert weekdays.window(monday) == RunWindow(friday_night, monday)
    # El sábado no hay corridas: el siguiente es el lunes.
    assert weekdays.next_after(cdmx(23, 23, 30)) == monday


def test_proximas_corridas() -> None:
    assert BENJI.upcoming(cdmx(26, 15), 3) == [cdmx(26, 23), cdmx(27, 7), cdmx(27, 15)]


def test_cuando_toca_lanzar_una_corrida() -> None:
    grace = timedelta(minutes=10)
    assert BENJI.due(cdmx(26, 7, 0, 30), grace) == cdmx(26, 7)
    assert BENJI.due(cdmx(26, 7, 9), grace) == cdmx(26, 7)
    # Pasados 10 minutos ya no se lanza: el reloj estuvo apagado.
    assert BENJI.due(cdmx(26, 7, 10), grace) is None
    assert BENJI.due(cdmx(26, 12), grace) is None


def test_el_margen_es_opcional() -> None:
    assert BENJI.window(cdmx(28, 15), timedelta(minutes=30)).start == cdmx(28, 6, 30)


def test_que_notas_le_tocan_a_la_ventana() -> None:
    window = RunWindow(cdmx(27, 23), cdmx(28, 7))
    assert window.contains(cdmx(27, 23))
    assert window.contains(cdmx(28, 6, 59))
    # Lo publicado justo a las 07:00 es de la corrida siguiente.
    assert not window.contains(cdmx(28, 7))
    assert not window.contains(cdmx(27, 22, 59))
    # Sin fecha no se puede saber si ya salió: no le toca.
    assert not window.contains(None)
