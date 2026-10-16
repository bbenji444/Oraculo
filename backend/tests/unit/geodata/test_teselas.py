"""Armado de comandos para generar PMTiles (sin ejecutar GDAL ni tippecanoe)."""

from pathlib import Path

import pytest

from app.geodata import teselas
from app.geodata.carga import PostgresTarget

TARGET = PostgresTarget("localhost", 5432, "monitor_noticias", "monitor", "secreto")
BY_NAME = {layer.name: layer for layer in teselas.LAYERS}


def test_zooms_de_la_especificacion() -> None:
    zooms = {name: (layer.min_zoom, layer.max_zoom) for name, layer in BY_NAME.items()}

    assert zooms == {
        "countries": (0, 6),
        "states": (2, 10),
        "municipalities": (5, 14),
        "localities": (10, 14),
    }


def test_exportacion_solo_lleva_atributos_del_mapa_y_sin_contrasena() -> None:
    command = teselas.build_export_command(BY_NAME["states"], TARGET, Path("/w/states.geojsonl"))

    sql = command[command.index("-sql") + 1]
    assert command[:4] == ["ogr2ogr", "-f", "GeoJSONSeq", "/w/states.geojsonl"]
    assert sql == (
        "SELECT id, code, name, display_prefix, level::text AS level, geom AS geom "
        "FROM regions WHERE level = 'state' ORDER BY id"
    )
    assert "secreto" not in " ".join(command)


def test_localidades_se_exportan_como_su_punto_representativo() -> None:
    command = teselas.build_export_command(
        BY_NAME["localities"], TARGET, Path("/w/localities.geojsonl")
    )

    assert "centroid AS geom" in command[command.index("-sql") + 1]


@pytest.mark.parametrize("name", ["states", "municipalities"])
def test_poligonos_comparten_bordes_y_llevan_id_numerico(name: str) -> None:
    command = teselas.build_tippecanoe_command(BY_NAME[name], Path("in"), Path("out.pmtiles"))

    assert "--detect-shared-borders" in command
    assert "--use-attribute-for-id=id" in command
    assert command[command.index("-l") + 1] == name
    assert command[command.index("-A") + 1] == "© INEGI · Natural Earth"
    assert command[-1] == "in"


def test_puntos_descartan_los_mas_densos_en_zoom_bajo() -> None:
    command = teselas.build_tippecanoe_command(
        BY_NAME["localities"], Path("in"), Path("out.pmtiles")
    )

    assert "--drop-densest-as-needed" in command
    assert "--detect-shared-borders" not in command
    assert [command[i + 1] for i, arg in enumerate(command) if arg == "-y"] == [
        "id",
        "code",
        "name",
        "display_prefix",
        "level",
    ]


def test_herramienta_que_falla_reporta_su_mensaje() -> None:
    with pytest.raises(teselas.TileGenerationError, match="false falló"):
        teselas.run_tool(["false"])
