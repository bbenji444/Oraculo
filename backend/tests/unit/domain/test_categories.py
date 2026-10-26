"""Categorías de noticias (F12.4, ADR-0029)."""

import importlib.util
from pathlib import Path

import pytest

from app.domain.categories import (
    MAX_RAW_LABEL_CHARS,
    Category,
    MissingOtherCategoryError,
    choose_category,
    other_category,
)
from app.domain.names import normalize_name

HUACHICOL = Category(7, "Huachicol y delitos contra hidrocarburos", "Robo de combustible")
NARCO = Category(1, "Narcotráfico y delitos contra la salud", "Drogas")
OTROS = Category(14, "Otros", "Lo demás", is_other=True)
CATALOG = [NARCO, HUACHICOL, OTROS]
MIGRATION = (
    Path(__file__).resolve().parents[3] / "alembic" / "versions" / "20261025_0026_categorias.py"
)


def test_elige_la_categoria_aunque_cambien_acentos_y_mayusculas() -> None:
    choice = choose_category(5, "narcotrafico y delitos contra la salud", "narcomenudeo", CATALOG)

    assert (choice.article_id, choice.category, choice.raw_label) == (5, NARCO, "narcomenudeo")


def test_una_categoria_inventada_va_a_otros_con_su_etiqueta() -> None:
    choice = choose_category(5, "Robo de vehículos", "  robo   de autos ", CATALOG)

    assert choice.category is OTROS
    assert choice.raw_label == "robo de autos"


def test_sin_respuesta_tambien_va_a_otros() -> None:
    assert choose_category(5, None, None, CATALOG) == choose_category(5, "", "", CATALOG)
    assert choose_category(5, None, None, CATALOG).category is OTROS
    assert choose_category(5, None, None, CATALOG).raw_label is None


def test_recorta_etiquetas_largas() -> None:
    label = choose_category(5, "Otros", "x" * 200, CATALOG).raw_label

    assert label is not None
    assert len(label) == MAX_RAW_LABEL_CHARS


def test_sin_otros_no_se_puede_clasificar() -> None:
    with pytest.raises(MissingOtherCategoryError):
        other_category([NARCO])


def test_la_siembra_usa_la_misma_normalizacion_y_tiene_un_solo_otros() -> None:
    spec = importlib.util.spec_from_file_location("migracion_0026", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    seed = module._SEED
    assert len(seed) == 14
    assert all(norm == normalize_name(name) for name, norm, _ in seed)
    assert [name for name, norm, _ in seed if norm == "OTROS"] == ["Otros"]
