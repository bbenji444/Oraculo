"""Presupuesto: consultas por búsqueda y créditos por mes."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.domain.budget import (
    MonthlyCredits,
    QueryBudgetExceededError,
    check_query_count,
    month_start,
)

MEXICO = timezone(timedelta(hours=-6))


def test_hasta_el_maximo_se_permite() -> None:
    check_query_count(10, 10)


def test_mas_del_maximo_se_rechaza_con_sugerencia() -> None:
    with pytest.raises(QueryBudgetExceededError, match="11 consultas y el máximo es 10"):
        check_query_count(11, 10)


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
