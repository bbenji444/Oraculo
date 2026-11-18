"""Presupuesto: consultas por búsqueda y créditos por mes."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.domain.budget import (
    MonthlyCredits,
    QueryBudgetExceededError,
    QueryCaps,
    check_query_count,
    month_start,
)
from app.domain.queries import Provider

MEXICO = timezone(timedelta(hours=-6))


CAPS = QueryCaps(paid=10, free=24)
RSS = Provider.GOOGLE_NEWS_RSS


def test_hasta_el_maximo_se_permite() -> None:
    check_query_count([Provider.SEARCHAPI] * 10 + [RSS] * 24, CAPS)


def test_mas_consultas_de_pago_que_el_maximo_se_rechaza_con_sugerencia() -> None:
    with pytest.raises(QueryBudgetExceededError, match="11 consultas de pago y el máximo es 10"):
        check_query_count([Provider.SEARCHAPI] * 11, CAPS)


def test_las_gratuitas_tienen_su_propio_tope() -> None:
    # ADR-0109: dos conceptos «como en Google» son 24 consultas al RSS; con
    # una más, el mensaje dice cómo bajarla.
    with pytest.raises(QueryBudgetExceededError, match="frases") as raised:
        check_query_count([RSS] * 12 + [RSS] * 12 + [Provider.GDELT], CAPS)

    assert raised.value.details == {"consultas": 25, "maximo": 24, "tipo": "gratuitas"}


def test_el_indice_local_no_cuenta() -> None:
    # Es nuestra base: consultarlo no le cuesta ni lo frena nadie.
    check_query_count([Provider.LOCAL_INDEX] * 50, QueryCaps(paid=1, free=1))


def test_las_gratuitas_no_gastan_el_tope_de_pago() -> None:
    check_query_count([RSS] * 20 + [Provider.BROWSERWORK_BING] * 2, QueryCaps(paid=1, free=24))


def test_el_mes_se_cuenta_en_hora_de_la_ciudad_de_mexico() -> None:
    # 1 de noviembre 03:00 UTC = 31 de octubre 21:00 en la CDMX: sigue octubre.
    assert month_start(datetime(2026, 11, 1, 3, 0, tzinfo=UTC), MEXICO) == datetime(
        2026, 10, 1, 6, 0, tzinfo=UTC
    )
    assert month_start(datetime(2026, 11, 1, 7, 0, tzinfo=UTC), MEXICO) == datetime(
        2026, 11, 1, 6, 0, tzinfo=UTC
    )


def test_reserva_hasta_el_tope_y_devuelve_lo_que_no_se_cobro() -> None:
    budget = MonthlyCredits(used=98, limit=100)

    assert budget.try_reserve(1) is True
    assert budget.try_reserve(1) is True
    assert budget.try_reserve(1) is False
    budget.release(1)
    assert budget.try_reserve(1) is True


def test_tope_cero_no_permite_gastar() -> None:
    assert MonthlyCredits(used=0, limit=0).try_reserve(1) is False
    assert MonthlyCredits(used=0, limit=0).try_reserve(0) is True
