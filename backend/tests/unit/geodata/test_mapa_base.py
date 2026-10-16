"""Mapa base: comandos de recorte, recursos del estilo e idempotencia (sin red)."""

import io
import zipfile
from pathlib import Path

from app.geodata import mapa_base
from app.geodata.descarga import sha256_file

PREFIX = f"basemaps-assets-{mapa_base.ASSETS_COMMIT}/"


def test_mundo_sin_bbox_y_mexico_con_bbox_y_zoom_aprobado() -> None:
    world, mexico = mapa_base.EXTRACTS

    world_cmd = mapa_base.build_extract_command(world, Path("/w/world.pmtiles"))
    mexico_cmd = mapa_base.build_extract_command(mexico, Path("/w/mexico.pmtiles"))

    assert world_cmd[1:4] == ["extract", mapa_base.PROTOMAPS_URL, "/w/world.pmtiles"]
    assert "--maxzoom=6" in world_cmd
    assert not any(arg.startswith("--bbox") for arg in world_cmd)
    assert "--maxzoom=14" in mexico_cmd
    assert "--bbox=-118.6,14.3,-86.5,32.9" in mexico_cmd


def make_assets_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for stack in ("Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"):
            zf.writestr(f"{PREFIX}fonts/{stack}/0-255.pbf", b"glifos")
        zf.writestr(f"{PREFIX}fonts/Noto Sans Devanagari Regular v1/0-255.pbf", b"no se usa")
        zf.writestr(f"{PREFIX}fonts/OFL.txt", "licencia")
        for name in ("dark.json", "dark.png", "dark@2x.json", "dark@2x.png", "light.json"):
            zf.writestr(f"{PREFIX}sprites/v4/{name}", name)
        zf.writestr(f"{PREFIX}sprites/v3/dark.json", "versión vieja")
    return buffer.getvalue()


def test_solo_extrae_las_fuentes_y_el_sprite_que_usa_el_estilo(tmp_path: Path) -> None:
    extracted = mapa_base.extract_assets(make_assets_zip(), tmp_path)

    names = sorted(p.relative_to(tmp_path).as_posix() for p in extracted)
    assert names == [
        "fonts/Noto Sans Italic/0-255.pbf",
        "fonts/Noto Sans Medium/0-255.pbf",
        "fonts/Noto Sans Regular/0-255.pbf",
        "fonts/OFL.txt",
        "sprites/v4/dark.json",
        "sprites/v4/dark.png",
        "sprites/v4/dark@2x.json",
        "sprites/v4/dark@2x.png",
    ]


def test_reconoce_un_recorte_ya_descargado_con_los_mismos_parametros(tmp_path: Path) -> None:
    world = mapa_base.EXTRACTS[0]
    (tmp_path / world.name).write_bytes(b"pmtiles")
    entry = {
        "name": world.name,
        "max_zoom": world.max_zoom,
        "bbox": None,
        "sha256": sha256_file(tmp_path / world.name),
    }
    manifest = {"protomaps_build": mapa_base.PROTOMAPS_BUILD, "files": [entry]}

    assert mapa_base._manifest_matches(manifest, world, tmp_path)
    assert not mapa_base._manifest_matches(
        {**manifest, "protomaps_build": "20200101"}, world, tmp_path
    )
    assert not mapa_base._manifest_matches(
        {**manifest, "files": [{**entry, "max_zoom": 5}]}, world, tmp_path
    )
    assert not mapa_base._manifest_matches({}, world, tmp_path)
    (tmp_path / world.name).write_bytes(b"otro contenido")
    assert not mapa_base._manifest_matches(manifest, world, tmp_path)
