"""Texturas de la Tierra (make geo-earth): comandos y flujo, sin red ni GDAL."""

import json
from pathlib import Path

from app.geodata import tierra


def test_georreferencia_el_mundo_entero_y_puede_igualar_el_tamano(tmp_path: Path) -> None:
    command = tierra.georeference_command(tmp_path / "a.jpg", tmp_path / "a.tif", (21600, 10800))

    assert command[:7] == ["gdal_translate", "-q", "-a_srs", "EPSG:4326", "-a_ullr", "-180", "90"]
    assert command[9:12] == ["-outsize", "21600", "10800"]
    assert "-outsize" not in tierra.georeference_command(tmp_path / "a", tmp_path / "b", None)


def test_la_noche_suma_las_luces_a_la_tierra_oscurecida_banda_por_banda(tmp_path: Path) -> None:
    command = tierra.night_command(tmp_path / "dia.tif", tmp_path / "luces.tif", tmp_path / "n.tif")

    calcs = [command[i + 1] for i, arg in enumerate(command) if arg == "--calc"]
    assert calcs == [
        "numpy.clip(A*0.1+D*1.1,0,255)",
        "numpy.clip(B*0.13+E*1.1,0,255)",
        "numpy.clip(C*0.22+F*1.1,0,255)",
    ]
    assert "--A_band=1" in command and "--F_band=3" in command
    assert "--overwrite" in command
    assert command[-1] == str(tmp_path / "n.tif")


def test_teselas_webp_sin_inventar_detalle(tmp_path: Path) -> None:
    translate, overviews = tierra.mbtiles_commands(tmp_path / "x.tif", tmp_path / "x.mbtiles", "x")

    assert "TILE_FORMAT=WEBP" in translate
    assert "ZOOM_LEVEL_STRATEGY=LOWER" in translate
    assert overviews[-6:] == ["2", "4", "8", "16", "32", "64"]
    assert tierra.mercator_command(tmp_path / "a", tmp_path / "b")[3] == "EPSG:3857"


def test_muestras_de_mapa_y_de_estrellas(tmp_path: Path) -> None:
    mexico, *_, stars = tierra.SAMPLES

    by_coords = tierra.sample_command(tmp_path / "d.tif", mexico, tmp_path / "m.jpg", 1200)
    by_pixels = tierra.sample_command(tmp_path / "s.jpg", stars, tmp_path / "s_out.jpg", 1200)

    assert by_coords[by_coords.index("-projwin") + 1 : by_coords.index("-projwin") + 5] == [
        "-118.5",
        "33.0",
        "-86.5",
        "14.0",
    ]
    start = by_pixels.index("-srcwin")
    assert by_pixels[start + 1 : start + 3] == ["5570", "2293"]


def test_flujo_completo_publica_teselas_estrellas_y_manifiesto(tmp_path: Path) -> None:
    work, output = tmp_path / "trabajo", tmp_path / "salida"
    commands: list[list[str]] = []

    def fake_download(source: tierra.Source, raw_dir: Path) -> Path:
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / source.filename
        path.write_bytes(source.key.encode())
        return path

    def fake_runner(command: list[str]) -> str:
        commands.append(command)
        # pmtiles convert deja el archivo que después se verifica y publica.
        if command[0].endswith("pmtiles") and command[1] == "convert":
            Path(command[3]).write_bytes(b"teselas")
        return ""

    def run(samples_only: bool) -> dict[str, object]:
        return tierra.run(
            work, output, samples_only=samples_only, fetch=fake_download, runner=fake_runner
        )

    samples = run(samples_only=True)
    manifest = run(samples_only=False)

    assert samples["files"] == []
    assert sum(1 for c in commands if c[0] == "gdal_translate" and "JPEG" in c) == 5
    files = manifest["files"]
    assert isinstance(files, list)
    names = [f["name"] for f in files]
    assert names == [
        "earth_day.pmtiles",
        "earth_night.pmtiles",
        "space/starmap_4k.jpg",
        "space/starmap_8k.jpg",
    ]
    saved = json.loads((output / tierra.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert saved["credit"].startswith("Imágenes: NASA")
    assert [d["key"] for d in saved["downloads"]] == [
        "blue_marble",
        "black_marble",
        "stars_4k",
        "stars_8k",
    ]
