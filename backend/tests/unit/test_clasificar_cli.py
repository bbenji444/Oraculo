"""Comando ``make clasificar`` (F12.4–F12.5): costo, opciones y quién actúa, sin red."""

import pytest

from app.application.use_cases.classify import BATCH_SIZE
from app.cli.clasificar import (
    _PROMPT_TOKENS_PER_BATCH,
    _TOKENS_IN_PER_NOTE,
    _TOKENS_OUT_PER_NOTE,
    authority_text,
    estimated_usage,
    parse_args,
)
from app.domain.authority import Authority


def test_cinco_notas_son_un_lote() -> None:
    usage = estimated_usage(5)

    assert usage.tokens_in == _PROMPT_TOKENS_PER_BATCH + 5 * _TOKENS_IN_PER_NOTE
    assert usage.tokens_out == 5 * _TOKENS_OUT_PER_NOTE


def test_26_notas_cobran_el_prompt_de_dos_lotes() -> None:
    # 25 por lote: la nota 26 abre un lote nuevo y repite el catálogo.
    assert estimated_usage(26).tokens_in == 2 * _PROMPT_TOKENS_PER_BATCH + 26 * _TOKENS_IN_PER_NOTE


def test_sin_opciones_no_guarda() -> None:
    args = parse_args([])

    assert args.aplicar is False
    assert args.busqueda is None


def test_notas_elegidas_por_id() -> None:
    assert parse_args(["--notas", "1382, 1463,1385"]).notas == [1382, 1463, 1385]


@pytest.mark.parametrize("value", ["abc", "", ",".join(str(i) for i in range(BATCH_SIZE + 1))])
def test_notas_invalidas_no_se_aceptan(value: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--notas", value])


def test_notas_solo_prueba_no_se_combina_con_aplicar() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--notas", "1", "--aplicar"])


@pytest.mark.parametrize(
    ("authority", "expected"),
    [
        (Authority.FGR, "FGR federal"),
        (Authority.STATE, "Fiscalía estatal (no cuenta para la FGR)"),
        (Authority.FGR_MENTION, "FGR solo mencionada (no cuenta para la FGR)"),
        (Authority.UNKNOWN, "No se sabe"),
        (None, "quién actúa: sin respuesta"),
    ],
)
def test_quien_actua_en_palabras(authority: Authority | None, expected: str) -> None:
    assert authority_text(authority) == expected
