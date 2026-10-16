"""Lectura de términos de búsqueda y de códigos de país (sin base de datos)."""

import json
from pathlib import Path

import pytest

from app.geodata.terminos import (
    CountryCodes,
    SearchTermsError,
    read_country_codes,
    read_search_terms,
)
from tests.unit.geodata.dbf_builder import write_dbf

REPO_ROOT = Path(__file__).resolve().parents[4]
NE_FIELDS = [("ADM0_A3", 3), ("ISO_A3", 3), ("ISO_A2_EH", 3), ("FIPS_10", 3), ("NAME_EN", 30)]


def test_terminos_agrupados_sin_repetir_y_con_espacios_limpios(tmp_path: Path) -> None:
    path = tmp_path / "search_terms.csv"
    path.write_text(
        "code,termino,nota\n09,Ciudad de  México,a\n09,CDMX,b\n09,CDMX,repetido\n15, Edomex ,c\n",
        encoding="utf-8",
    )

    assert read_search_terms(path) == {"09": ["Ciudad de México", "CDMX"], "15": ["Edomex"]}


def test_termino_vacio_es_error_con_su_linea(tmp_path: Path) -> None:
    path = tmp_path / "search_terms.csv"
    path.write_text("code,termino,nota\n09,CDMX,a\n15,  ,vacío\n", encoding="utf-8")

    with pytest.raises(SearchTermsError, match="línea 3"):
        read_search_terms(path)


def test_terminos_reales_del_repositorio() -> None:
    terms = read_search_terms(REPO_ROOT / "geodata" / "search_terms.csv")

    assert terms["09"] == ["Ciudad de México", "CDMX"]
    # El estado 15 nunca se busca como "México" a secas (ADR-0009).
    assert terms["15"] == ["Estado de México", "Edomex"]
    assert "México" not in terms["15"]


def test_codigos_de_pais_desde_el_dbf_de_natural_earth(tmp_path: Path) -> None:
    shp = tmp_path / "ne.shp"
    write_dbf(
        shp.with_suffix(".dbf"),
        NE_FIELDS,
        [
            [b"MEX", b"MEX", b"MX", b"MX", b"Mexico"],
            # España: ISO y FIPS distintos.
            [b"ESP", b"ESP", b"ES", b"SP", b"Spain"],
            # Noruega: sin ISO_A3 ni FIPS en Natural Earth.
            [b"NOR", b"-99", b"NO", b"-99", b"Norway"],
        ],
    )

    assert read_country_codes(shp) == [
        CountryCodes("MEX", "MX", "MX", "Mexico"),
        CountryCodes("ESP", "ES", "SP", "Spain"),
        CountryCodes("NOR", "NO", None, "Norway"),
    ]


def test_iso_a3_repetido_usa_adm0_como_el_cargador(tmp_path: Path) -> None:
    path = tmp_path / "paises.geojson"
    features = [
        {
            "properties": {
                "ADM0_A3": a,
                "ISO_A3": iso,
                "ISO_A2_EH": "XX",
                "FIPS_10": "",
                "NAME_EN": a,
            }
        }
        for a, iso in (("AAA", "DUP"), ("BBB", "DUP"), ("CCC", "CCC"))
    ]
    path.write_text(json.dumps({"features": features}), encoding="utf-8")

    assert [c.code for c in read_country_codes(path)] == ["AAA", "BBB", "CCC"]
    assert all(c.fips_code is None for c in read_country_codes(path))
