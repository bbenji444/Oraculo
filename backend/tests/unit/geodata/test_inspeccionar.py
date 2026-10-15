"""Comando inspeccionar de punta a punta con datos de juguete (sin GDAL ni red)."""

import io
import json
import logging
import zipfile
from pathlib import Path

import pytest

from app.geodata import inspeccion, inspeccionar
from app.geodata.fuentes import INEGI_MG, NATURAL_EARTH_COUNTRIES
from tests.unit.geodata.dbf_builder import write_dbf

INEGI_ROWS = {
    "00ent": [[b"09", "Ciudad de México".encode()], [b"10", b"Durango"]],
    "00mun": [[b"09007", b"Iztapalapa"], [b"10021", "Peñón Blanco".encode()]],
    "00l": [[b"090070001", b"Iztapalapa"]],
    "00lpr": [[b"100210001", "La Cañada".encode()], [b"100210002", "San José".encode()]],
}


def dbf_bytes(tmp_path: Path, fields: list[tuple[str, int]], rows: list[list[bytes]]) -> bytes:
    path = tmp_path / "tmp.dbf"
    write_dbf(path, fields, rows)
    return path.read_bytes()


def build_inputs(tmp_path: Path, *, missing_municipality: bool = False) -> Path:
    raw_dir = tmp_path / "raw"
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        for layer, rows in INEGI_ROWS.items():
            data = dbf_bytes(tmp_path, [("CVEGEO", 9), ("NOMGEO", 30)], rows)
            zf.writestr(f"conjunto_de_datos/{layer}.dbf", data)
            zf.writestr(f"conjunto_de_datos/{layer}.cpg", "UTF-8")
            for ext in (".shp", ".shx", ".prj"):
                zf.writestr(f"conjunto_de_datos/{layer}{ext}", "x")
        catalog = "Áreas,,,\nClave,Estado,Clave,Municipio\n09,CDMX,007,Iztapalapa\n"
        if not missing_municipality:
            catalog += "10,Durango,021,Peñón Blanco\n"
        catalog += "10,Durango,099,Fantasma\n" if missing_municipality else ""
        zf.writestr("catalogos/áreas_municipales.csv", catalog.encode("cp1252"))
    inegi_path = raw_dir / INEGI_MG.relative_path
    inegi_path.parent.mkdir(parents=True)
    inegi_path.write_bytes(inner.getvalue())

    ne_rows = [
        [b"MEX", b"MEX", "México".encode()],
        [b"FRA", b"-99", b"Francia"],
        [b"PER", b"PER", "Perú".encode()],
    ]
    ne_path = raw_dir / NATURAL_EARTH_COUNTRIES.relative_path
    ne_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(ne_path, "w") as zf:
        zf.writestr(
            "ne_10m_admin_0_countries.dbf",
            dbf_bytes(tmp_path, [("ADM0_A3", 3), ("ISO_A3", 3), ("NAME_ES", 40)], ne_rows),
        )
        zf.writestr("ne_10m_admin_0_countries.cpg", "UTF-8")
        zf.writestr("ne_10m_admin_0_countries.prj", "x")
    return raw_dir


@pytest.fixture(autouse=True)
def fake_epsg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspeccion, "detect_epsg", lambda path: "EPSG:6372")
    monkeypatch.setattr(inspeccionar, "detect_epsg", lambda path: "EPSG:4326")


def test_reporta_capas_catalogo_ejemplos_y_natural_earth(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    raw_dir = build_inputs(tmp_path)
    inspection_path = tmp_path / "INSPECCION.json"

    summary = inspeccionar.run(raw_dir, tmp_path / "trabajo", inspection_path)

    saved = json.loads(inspection_path.read_text(encoding="utf-8"))
    assert saved == summary
    assert saved["inegi"]["00mun"] == {
        "epsg": "EPSG:6372",
        "encoding": "utf-8",
        "records": 2,
        "duplicate_codes": 0,
    }
    assert saved["inegi_municipal_catalog"] == {
        "count": 2,
        "missing_in_layer": [],
        "extra_in_layer": [],
    }
    assert {e["name"] for e in saved["examples"]} >= {"Peñón Blanco", "La Cañada"}
    assert saved["natural_earth"] == {"encoding": "utf-8", "records": 3, "missing_iso_a3": 1}
    assert saved["localities"] == {"polygons": 1, "points": 2, "in_both": 0, "distinct": 3}
    assert "Nombres en español de muestra: Francia, México, Perú" in caplog.text


def test_avisa_si_el_catalogo_no_coincide_con_los_poligonos(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    raw_dir = build_inputs(tmp_path, missing_municipality=True)

    summary = inspeccionar.run(raw_dir, tmp_path / "trabajo", tmp_path / "I.json")

    catalog = summary["inegi_municipal_catalog"]
    assert catalog == {
        "count": 2,
        "missing_in_layer": ["10099"],
        "extra_in_layer": ["10021"],
    }
    assert "sin polígono" in caplog.text
