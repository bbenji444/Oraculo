"""Inspección de geodatos con archivos pequeños construidos en la prueba."""

import zipfile
from pathlib import Path

import pytest

from app.geodata import inspeccion
from tests.unit.geodata.dbf_builder import write_dbf

PARTS = (".shp", ".dbf")


def plan(layers: list[str]) -> inspeccion.ExtractionPlan:
    return inspeccion.ExtractionPlan(tuple(layers), "conjunto_de_datos", PARTS, "municipales.csv")


def make_zip(path: Path, layers: list[str], catalog: str | None) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for layer in layers:
            for ext in PARTS:
                zf.writestr(f"conjunto_de_datos/{layer}{ext}", f"{layer}{ext}")
        zf.writestr("conjunto_de_datos/00a.shp", "AGEB que no se usa")
        if catalog is not None:
            zf.writestr(catalog, "catálogo")


def test_extrae_solo_las_capas_pedidas_y_el_catalogo(tmp_path: Path) -> None:
    zip_path = tmp_path / "mg.zip"
    make_zip(zip_path, ["00ent", "00mun"], "catalogos/áreas_municipales.csv")

    extracted = inspeccion.extract_layers(zip_path, tmp_path / "out", plan(["00ent", "00mun"]))

    names = sorted(p.relative_to(tmp_path / "out").as_posix() for p in extracted)
    assert names == [
        "catalogos/catalogo_municipal.csv",
        "conjunto_de_datos/00ent.dbf",
        "conjunto_de_datos/00ent.shp",
        "conjunto_de_datos/00mun.dbf",
        "conjunto_de_datos/00mun.shp",
    ]
    assert not (tmp_path / "out/conjunto_de_datos/00a.shp").exists()


def test_extraccion_repetida_no_reescribe(tmp_path: Path) -> None:
    zip_path = tmp_path / "mg.zip"
    make_zip(zip_path, ["00ent"], "c/municipales.csv")
    args = (zip_path, tmp_path / "out", plan(["00ent"]))
    first = inspeccion.extract_layers(*args)
    mtime = first[0].stat().st_mtime_ns

    inspeccion.extract_layers(*args)

    assert first[0].stat().st_mtime_ns == mtime


def test_falta_una_capa(tmp_path: Path) -> None:
    zip_path = tmp_path / "mg.zip"
    make_zip(zip_path, ["00ent"], "c/municipales.csv")

    with pytest.raises(inspeccion.InspectionError, match="00mun"):
        inspeccion.extract_layers(zip_path, tmp_path / "out", plan(["00mun"]))


def test_falta_el_catalogo(tmp_path: Path) -> None:
    zip_path = tmp_path / "mg.zip"
    make_zip(zip_path, ["00ent"], None)

    with pytest.raises(inspeccion.InspectionError, match="catálogo"):
        inspeccion.extract_layers(zip_path, tmp_path / "out", plan(["00ent"]))


def test_ejemplos_priorizan_enie_y_completan_con_acentos() -> None:
    rows = [
        (b"05006", "Castaños".encode()),
        (b"01001", b"Aguascalientes"),
        (b"05002", "Acuña".encode()),
        (b"05002", "Acuña".encode()),
        (b"10021", "Peñón Blanco".encode()),
        (b"01008", "San José de Gracia".encode()),
        (b"01009", "Tepezalá".encode()),
        (b"20001", "Cañada".encode()),
    ]

    examples = inspeccion.pick_examples(rows, "utf-8", 5)

    assert [e.name for e in examples] == [
        "Castaños",
        "Acuña",
        "Peñón Blanco",
        "San José de Gracia",
        "Tepezalá",
    ]
    assert examples[1].raw_hex == "41 63 75 c3 b1 61"


def test_catalogo_ignora_titulos_y_arma_claves_completas(tmp_path: Path) -> None:
    csv_path = tmp_path / "catalogo.csv"
    csv_path.write_bytes(
        "Áreas Geoestadísticas Municipales,,,\n"
        '"Marco Geoestadístico, 2025",,,\n'
        "Clave Estatal,Estado,Clave Municipal,Municipio\n"
        "09,Ciudad de México,007,Iztapalapa\n"
        "5,Coahuila de Zaragoza,2,Acuña\n".encode("cp1252")
    )

    codes, encoding = inspeccion.read_catalog_codes(csv_path)

    assert codes == {"09007", "05002"}
    assert encoding == "cp1252"


def test_inspecciona_una_capa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_dbf(
        tmp_path / "00mun.dbf",
        [("CVEGEO", 5), ("NOMGEO", 30)],
        [[b"09007", b"Iztapalapa"], [b"10021", "Peñón Blanco".encode()], [b"09007", b"Otro"]],
    )
    (tmp_path / "00mun.cpg").write_text("UTF-8", encoding="ascii")
    monkeypatch.setattr(inspeccion, "detect_epsg", lambda path: "EPSG:6372")

    result = inspeccion.inspect_layer(tmp_path, "00mun", "municipios")

    assert result.record_count == 3
    assert result.epsg == "EPSG:6372"
    assert result.encoding.chosen == "utf-8"
    assert result.encoding.agrees_with_declared is True
    assert result.duplicate_codes == 1
