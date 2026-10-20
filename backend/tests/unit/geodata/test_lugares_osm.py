"""Carga de colonias de OpenStreetMap (ADR-0020): comando de GDAL y nombres."""

import re
from pathlib import Path

from app.geodata.carga import PostgresTarget
from app.geodata.lugares_osm import _PREFIX_PATTERN, READ_ZOOM, build_command

TARGET = PostgresTarget(host="localhost", port=5432, dbname="x", user="u", password="p")


def test_lee_la_capa_de_lugares_a_zoom_13_y_solo_lo_necesario() -> None:
    command = build_command(Path("trabajo/basemap_mexico.pmtiles"), TARGET)

    assert command[:3] == ["ogr2ogr", "-f", "PostgreSQL"]
    assert "places" in command
    assert f"ZOOM_LEVEL={READ_ZOOM}" in command
    assert command[command.index("-select") + 1] == "mvt_id,kind,kind_detail,name,wikidata"
    # La contraseña no va en el comando (viaja en PGPASSWORD).
    assert "password" not in " ".join(command)


def test_el_nucleo_del_nombre_quita_la_palabra_generica() -> None:
    # La expresión se usa en PostgreSQL; con la sintaxis común también vale en Python.
    def core(name: str) -> str:
        return re.sub(_PREFIX_PATTERN, "", name)

    assert core("COLONIA ROMA NORTE") == "ROMA NORTE"
    assert core("PUEBLO SANTA CRUZ MEYEHUALCO") == "SANTA CRUZ MEYEHUALCO"
    assert core("BARRIO DE SANTIAGO") == "SANTIAGO"
    assert core("POLANCO") == "POLANCO"
    # "Colonial" no es "colonia": solo se quita la palabra completa.
    assert core("COLONIAL IZTAPALAPA") == "COLONIAL IZTAPALAPA"
