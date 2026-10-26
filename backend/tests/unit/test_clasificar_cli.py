"""Comando ``make clasificar`` (F12.4): la estimación de costo y las opciones, sin red."""

from app.cli.clasificar import (
    _PROMPT_TOKENS_PER_BATCH,
    _TOKENS_IN_PER_NOTE,
    _TOKENS_OUT_PER_NOTE,
    estimated_usage,
    parse_args,
)


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
