"""Criterio de reactivación de GDELT (ADR-0012): D1 una vez al día, 2 días con notas."""

from datetime import UTC, date, datetime

from app.application.ports.provider_log import QueryRun, QueryStatus
from app.cli.diagnostico_gdelt import D1_TEXT, d1_query, status_from

TODAY = date(2026, 10, 18)


def run(day: int, hour_utc: int, status: QueryStatus = "ok", results: int = 0) -> QueryRun:
    return QueryRun(datetime(2026, 10, day, hour_utc, 0, tzinfo=UTC), status, results)


def test_sin_envios_no_se_ha_corrido_ni_se_cumple() -> None:
    status = status_from([], TODAY)

    assert (status.ran_today, status.good_days, status.criterion_met) == (False, (), False)


def test_el_dia_se_cuenta_en_hora_de_la_ciudad_de_mexico() -> None:
    # 19 de octubre 03:00 UTC = 18 de octubre 21:00 en la CDMX: ya se corrió "hoy".
    assert status_from([run(19, 3, "error")], TODAY).ran_today is True
    assert status_from([run(18, 3, "error")], TODAY).ran_today is False


def test_respuestas_vacias_o_fallidas_no_cuentan() -> None:
    runs = [run(16, 18, "error"), run(17, 18, "ok", 0), run(18, 18, "ok", 0)]

    assert status_from(runs, TODAY).good_days == ()


def test_dos_dias_distintos_con_notas_cumplen_el_criterio() -> None:
    one_day = [run(16, 18, "ok", 40), run(16, 20, "ok", 12)]
    two_days = [*one_day, run(18, 18, "ok", 7)]

    assert status_from(one_day, TODAY).criterion_met is False
    status = status_from(two_days, TODAY)
    assert status.good_days == (date(2026, 10, 16), date(2026, 10, 18))
    assert status.criterion_met is True


def test_d1_es_la_consulta_del_diagnostico() -> None:
    query = d1_query(TODAY)

    assert query.text == D1_TEXT == "gobierno sourcelang:spanish"
    assert query.window.relative_days == 1
