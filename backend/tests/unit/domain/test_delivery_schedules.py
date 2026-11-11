"""Reglas de los envíos programados (ADR-0046): validar, topes y agrupar corridas."""

from datetime import datetime, timedelta
from typing import Any, cast

import pytest

from app.application.clock import MEXICO_CITY
from app.domain.delivery_schedules import (
    MAX_DAILY_RUNS_USER,
    ScheduledItem,
    ScheduleDraft,
    check_daily_limit,
    daily_runs,
    due_runs,
    topic_key,
)
from app.domain.errors import DeliveryValidationError
from app.domain.schedule import RunSchedule

GRACE = timedelta(minutes=10)
# Martes 11/11/2026 a las 16:00 en la Ciudad de México.
AT_1600 = datetime(2026, 11, 11, 16, 0, tzinfo=MEXICO_CITY)


def draft(
    times: tuple[int, ...],
    *,
    concepts: tuple[int, ...] = (3,),
    region: int = 14,
    days: tuple[int, ...] = (),
    active: bool = True,
) -> ScheduleDraft:
    return ScheduleDraft("Envío", concepts, region, RunSchedule(times, days), (1,), active)


def test_un_envio_valido_queda_limpio() -> None:
    clean = ScheduleDraft.validated(
        name="  Extorsión   Jalisco ",
        concept_ids=[5, 3, 3],
        region_id=14,
        times=[1200, 960],
        days=[1, 2, 3, 4, 5],
        recipient_ids=[2, 1],
    )

    assert (clean.name, clean.concept_ids, clean.schedule.times) == (
        "Extorsión Jalisco",
        (3, 5),
        (960, 1200),
    )
    assert (clean.schedule.days, clean.recipient_ids, clean.topic) == (
        (1, 2, 3, 4, 5),
        (1, 2),
        "c=3,5|r=14",
    )


@pytest.mark.parametrize(
    ("changes", "campo"),
    [
        ({"name": "  "}, "name"),
        ({"concept_ids": []}, "concept_ids"),
        ({"concept_ids": [1, 2, 3, 4, 5, 6]}, "concept_ids"),
        ({"times": []}, "times"),
        # Dos horas a menos de una hora se encimarían.
        ({"times": [960, 990]}, "times"),
        ({"days": [8]}, "days"),
    ],
)
def test_lo_que_no_es_valido_dice_en_que_campo(changes: dict[str, Any], campo: str) -> None:
    base: dict[str, Any] = {
        "name": "Envío",
        "concept_ids": [3],
        "region_id": 14,
        "times": [960],
    }
    with pytest.raises(DeliveryValidationError) as error:
        ScheduleDraft.validated(**{**base, **changes})

    problems = cast(list[dict[str, str]], error.value.details["problemas"])
    assert problems[0]["campo"] == campo


def test_el_tope_cuenta_el_dia_con_mas_corridas() -> None:
    diario = draft((420, 900))
    solo_lunes = draft((600,), days=(1,))
    apagado = draft((1200,), active=False)

    assert daily_runs([diario, solo_lunes, apagado]) == 3
    # Con el de los lunes ya suma 3: uno más diario pasa del tope.
    check_daily_limit(draft((1300,), days=(2,)), [diario, solo_lunes], MAX_DAILY_RUNS_USER)
    with pytest.raises(DeliveryValidationError, match="hasta 3 corridas"):
        check_daily_limit(draft((1300,)), [diario, solo_lunes], MAX_DAILY_RUNS_USER)
    check_daily_limit(draft((1300,)), [diario, solo_lunes], None)


def test_a_su_hora_cada_envio_pide_su_corrida_desde_su_hora_anterior() -> None:
    tarde = ScheduledItem(1, draft((960, 1200)))
    otro_tema = ScheduledItem(2, draft((960,), concepts=(7,)))
    a_las_8 = ScheduledItem(3, draft((1200,)))

    runs = due_runs([tarde, otro_tema, a_las_8], AT_1600 + timedelta(seconds=30), GRACE)

    assert [(r.topic, r.schedule_ids) for r in runs] == [("c=3|r=14", (1,)), ("c=7|r=14", (2,))]
    # La de las 16:00 del envío de 16:00 y 20:00 cubre desde las 20:00 de ayer.
    assert runs[0].window.start == datetime(2026, 11, 10, 20, 0, tzinfo=MEXICO_CITY)
    assert runs[0].slot == AT_1600


def test_los_que_piden_lo_mismo_comparten_una_corrida() -> None:
    # Benji y Ana con la FGR de siempre: una sola corrida con IA para los dos.
    benji = ScheduledItem(1, draft((420, 900, 1380)))
    ana = ScheduledItem(2, draft((420, 900, 1380)))
    # Mismo tema y hora, pero otro periodo (su hora anterior es otra): aparte.
    pepe = ScheduledItem(3, draft((900, 960)))

    runs = due_runs([benji, ana, pepe], AT_1600, GRACE)

    assert [r.schedule_ids for r in runs] == [(3,)]
    at_1500 = AT_1600 - timedelta(hours=1)
    grouped = due_runs([benji, ana, pepe], at_1500, GRACE)
    assert sorted(r.schedule_ids for r in grouped) == [(1, 2), (3,)]


def test_fuera_de_su_hora_o_apagado_no_pide_nada() -> None:
    assert due_runs([ScheduledItem(1, draft((960,)))], AT_1600 + GRACE, GRACE) == []
    assert due_runs([ScheduledItem(1, draft((960,), active=False))], AT_1600, GRACE) == []
    # Solo los lunes: el martes no corre.
    assert due_runs([ScheduledItem(1, draft((960,), days=(1,)))], AT_1600, GRACE) == []


def test_la_llave_del_tema_no_depende_del_orden() -> None:
    assert topic_key([14, 3, 3], 9) == topic_key([3, 14], 9) == "c=3,14|r=9"
