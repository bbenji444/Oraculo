"""Partes del cargador que no necesitan base de datos ni GDAL."""

import json
from pathlib import Path

import pytest

from app.geodata import carga, cargar
from app.geodata.carga import LayerInput, PostgresTarget

TARGET = PostgresTarget("localhost", 5432, "monitor_noticias", "monitor", "secreto")


def layer(path: Path, *, encoding: str = "utf-8", is_point: bool = False) -> LayerInput:
    return LayerInput("inegi_mun", path, encoding, is_point, ("CVEGEO", "NOMGEO"))


def test_comando_ogr2ogr_reproyecta_por_lotes_y_sin_contrasena() -> None:
    command = carga.build_ogr2ogr_command(layer(Path("/w/00mun.shp"), encoding="cp1252"), TARGET)

    joined = " ".join(command)
    assert command[:4] == [
        "ogr2ogr",
        "-f",
        "PostgreSQL",
        "PG:host=localhost port=5432 dbname=monitor_noticias user=monitor",
    ]
    assert "-nln staging_geo.inegi_mun" in joined
    assert "-t_srs EPSG:4326" in joined
    assert "-nlt PROMOTE_TO_MULTI" in joined
    assert "-gt 20000" in joined
    assert "SHAPE_ENCODING CP1252" in joined
    assert "-select CVEGEO,NOMGEO" in joined
    assert "secreto" not in joined


def test_capa_de_puntos_se_carga_como_punto() -> None:
    command = carga.build_ogr2ogr_command(layer(Path("/w/x.shp"), is_point=True), TARGET)

    assert command[command.index("-nlt") + 1] == "POINT"


def test_encoding_sin_equivalente_en_gdal() -> None:
    with pytest.raises(carga.GeodataLoadError, match="koi8"):
        carga.build_ogr2ogr_command(layer(Path("/w/x.shp"), encoding="koi8"), TARGET)


def test_nombre_de_tabla_inseguro_se_rechaza() -> None:
    bad = LayerInput("x; DROP TABLE regions", Path("/w/x.shp"), "utf-8", False, ("A",))

    with pytest.raises(carga.GeodataLoadError, match="no permitido"):
        carga.build_ogr2ogr_command(bad, TARGET)


def test_alias_agrupados_sin_repetir(tmp_path: Path) -> None:
    path = tmp_path / "aliases.csv"
    path.write_text(
        "code,alias,nota\n09,CDMX,a\n09,DF,b\n09,CDMX,repetido\n15058,Neza,c\n15, ,vacío\n",
        encoding="utf-8",
    )

    assert carga.read_aliases(path) == {"09": ["CDMX", "DF"], "15058": ["Neza"]}


def test_alias_reales_del_repositorio_son_legibles() -> None:
    aliases = carga.read_aliases(Path(__file__).resolve().parents[4] / "geodata" / "aliases.csv")

    assert aliases["09"] == ["CDMX", "DF", "Distrito Federal", "la capital del país"]
    assert aliases["15058"] == ["Neza", "Ciudad Nezahualcóyotl"]


def test_entradas_fuera_de_la_carpeta_de_trabajo_se_copian_con_sus_hermanos(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "windows"
    source_dir.mkdir()
    for ext in (".shp", ".dbf", ".prj"):
        (source_dir / f"00mun{ext}").write_bytes(f"contenido {ext}".encode())
    work_dir = tmp_path / "linux"
    inside = work_dir / "inegi" / "00ent.shp"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"ya extraido")
    inputs = carga.LoadInputs(
        countries=layer(inside),
        states=layer(inside),
        municipalities=layer(source_dir / "00mun.shp"),
        locality_points=layer(inside, is_point=True),
        locality_polygons=layer(inside),
        aliases_csv=tmp_path / "aliases.csv",
        inegi_source="x",
        natural_earth_source="y",
    )

    staged = carga.stage_inputs(inputs, work_dir)

    assert staged.states.path == inside
    assert staged.municipalities.path == work_dir / "entrada" / "00mun.shp"
    assert (work_dir / "entrada" / "00mun.dbf").read_bytes() == b"contenido .dbf"


def test_copia_que_no_coincide_es_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.shp").write_bytes(b"datos")
    hashes = iter(["original", "dañada"])
    monkeypatch.setattr(carga, "sha256_file", lambda path: next(hashes))

    with pytest.raises(carga.GeodataLoadError, match="no coincide"):
        carga.copy_verified(tmp_path / "a.shp", tmp_path / "copia" / "a.shp")


# --- Comando cargar ---------------------------------------------------------------


def write_inspection(path: Path) -> dict[str, object]:
    inspection: dict[str, object] = {
        "inegi": {code: {"encoding": "utf-8"} for code in ("00ent", "00mun", "00l", "00lpr")},
        "natural_earth": {"encoding": "utf-8"},
    }
    path.write_text(json.dumps(inspection), encoding="utf-8")
    return inspection


def test_sin_inspeccion_pide_correr_geo_inspect(tmp_path: Path) -> None:
    with pytest.raises(cargar.MissingInspectionError, match="make geo-inspect"):
        cargar.read_inspection(tmp_path / "INSPECCION.json")


def test_arma_entradas_desde_la_inspeccion(tmp_path: Path) -> None:
    inspection = write_inspection(tmp_path / "INSPECCION.json")
    shp_dir = tmp_path / "inegi" / "conjunto_de_datos"
    shp_dir.mkdir(parents=True)
    for code in ("00ent", "00mun", "00l", "00lpr"):
        (shp_dir / f"{code}.shp").write_bytes(b"x")
    (tmp_path / "natural_earth").mkdir()
    (tmp_path / "natural_earth" / "ne_10m_admin_0_countries.shp").write_bytes(b"x")

    inputs = cargar.build_inputs(cargar.read_inspection(tmp_path / "INSPECCION.json"), tmp_path)

    assert inspection["natural_earth"] == {"encoding": "utf-8"}
    assert inputs.locality_points.is_point
    assert inputs.municipalities.path == shp_dir / "00mun.shp"
    assert inputs.countries.fields == ("ADM0_A3", "ISO_A3", "NAME_ES", "NAME")
    assert "Encuesta Intercensal" not in inputs.natural_earth_source


def test_falta_una_capa_extraida(tmp_path: Path) -> None:
    write_inspection(tmp_path / "INSPECCION.json")

    # Ninguna capa está extraída: el mensaje indica cómo resolverlo.
    with pytest.raises(cargar.MissingInspectionError, match="make geo-inspect"):
        cargar.build_inputs(cargar.read_inspection(tmp_path / "INSPECCION.json"), tmp_path)
