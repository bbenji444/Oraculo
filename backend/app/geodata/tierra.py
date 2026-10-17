"""Comando ``make geo-earth``: texturas de la Tierra y del espacio (ADR-0017).

Descarga imágenes de la NASA (uso libre con crédito) y genera lo que dibuja
el globo, todo servido por nginx desde ``geodata/output``. Nunca se piden a
terceros desde el navegador (ADR-0004):

- ``earth_day.pmtiles``: Blue Marble Next Generation (julio 2004, ~2 km/píxel).
- ``earth_night.pmtiles``: la misma Tierra oscurecida y con tinte azul, más
  las luces de Black Marble 2016 sumadas encima. MapLibre no mezcla capas
  raster, por eso la mezcla se hace aquí, píxel a píxel, con ``gdal_calc.py``.
- ``space/starmap_4k.jpg`` y ``space/starmap_8k.jpg``: estrellas y Vía Láctea
  (Deep Star Maps 2012, coordenadas celestes) para el fondo de three.js.

Pasos: descargar con reintentos y SHA-256 → georreferenciar (las imágenes son
equirectangulares del mundo entero) → mezclar la noche → reproyectar a Web
Mercator → MBTiles WebP con sus niveles → ``pmtiles convert`` y
``pmtiles verify`` → copiar verificado a ``geodata/output`` → ``TIERRA.json``.

``--muestra`` solo descarga y genera 5 recortes JPG para aprobar cómo se ven
antes de procesar todo (CLAUDE.md §2.6).

Uso: ``python -m app.geodata.tierra [--muestra]``

No hace: no toca la base de datos ni las capas de INEGI.
"""

import argparse
import json
import logging
import time
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.config import get_settings
from app.geodata.carga import copy_verified
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.descarga import (
    HTTP_TIMEOUT_SECONDS,
    GeodataDownloadError,
    _with_retries,
    sha256_file,
    utc_now_iso,
)
from app.geodata.fuentes import REPO_ROOT
from app.geodata.teselas import PMTILES_BIN, run_tool

logger = logging.getLogger(__name__)

OUTPUT_DIR = REPO_ROOT / "geodata" / "output"
MANIFEST_NAME = "TIERRA.json"
SPACE_DIR_NAME = "space"
SAMPLES_DIR_NAME = "muestras_tierra"
CREDIT = "Imágenes: NASA Earth Observatory (Blue Marble, Black Marble) · NASA SVS (Deep Star Maps)"
LICENSE = "Imágenes de la NASA: uso libre con crédito (https://www.visibleearth.nasa.gov/image-use-policy)"

# Extensión de una imagen equirectangular del mundo entero (oeste, norte, este, sur).
WORLD_ULLR = ("-180", "90", "180", "-90")
# Web Mercator no llega a los polos: se recorta en ±85.0511° (límite estándar).
MERCATOR_BOUNDS = ("-20037508.34", "-20037508.34", "20037508.34", "20037508.34")
# Ancho de la Tierra de día (Blue Marble 21600×10800): la noche se lleva a lo mismo.
DAY_WIDTH, DAY_HEIGHT = 21600, 10800
# Calidad WebP: 80 deja la textura limpia a zoom 6 y pesa la mitad que 95.
WEBP_QUALITY = 80
# Zoom máximo: la imagen de ~2 km/píxel equivale a zoom 6 (2.4 km/píxel); más
# arriba solo se inventaría detalle (ADR-0017).
MAX_ZOOM = 6
# Niveles reducidos (gdaladdo) para los zooms 5 a 0.
OVERVIEW_FACTORS = ("2", "4", "8", "16", "32", "64")

# Mezcla de la noche (valores 0–255 por banda). La Tierra de día se oscurece al
# ~15 % con un tinte azul (como se ve iluminada solo por la luna) y las luces se
# suman a 1.1 para que las ciudades brillen. Ajuste visual aprobado con las
# muestras (CLAUDE.md §2.6).
NIGHT_DAY_FACTORS = (0.10, 0.13, 0.22)
NIGHT_LIGHT_GAIN = 1.1


@dataclass(frozen=True, slots=True)
class Source:
    """Una imagen de la NASA.

    Attributes:
        key: Identificador.
        title: Nombre legible.
        url: Descarga oficial.
        filename: Nombre local.
    """

    key: str
    title: str
    url: str
    filename: str


BLUE_MARBLE = Source(
    "blue_marble",
    "Blue Marble Next Generation, julio 2004, relieve y batimetría (21600×10800)",
    "https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/"
    "bmng-topography-bathymetry/july/world.topo.bathy.200407.3x21600x10800.jpg",
    "world.topo.bathy.200407.3x21600x10800.jpg",
)
BLACK_MARBLE = Source(
    "black_marble",
    "Black Marble 2016, luces nocturnas (3 km, 13500×6750)",
    "https://assets.science.nasa.gov/content/dam/science/esd/eo/images/imagerecords/"
    "144000/144898/BlackMarble_2016_3km.jpg",
    "BlackMarble_2016_3km.jpg",
)
STARS_4K = Source(
    "stars_4k",
    "Deep Star Maps 2012, coordenadas celestes (4096×2048)",
    "https://svs.gsfc.nasa.gov/vis/a000000/a003800/a003895/starmap_4k.jpg",
    "starmap_4k.jpg",
)
STARS_8K = Source(
    "stars_8k",
    "Deep Star Maps 2012, coordenadas celestes (8192×4096)",
    "https://svs.gsfc.nasa.gov/vis/a000000/a003800/a003895/starmap_8k.jpg",
    "starmap_8k.jpg",
)
SOURCES = (BLUE_MARBLE, BLACK_MARBLE, STARS_4K, STARS_8K)


@dataclass(frozen=True, slots=True)
class Sample:
    """Un recorte para revisar a mano antes de procesar todo.

    Attributes:
        name: Nombre del archivo JPG.
        title: Qué muestra.
        texture: ``day``, ``night`` o ``stars``.
        window: Oeste, norte, este, sur (grados), o fracciones de la imagen
            de estrellas (izquierda, arriba, derecha, abajo).
    """

    name: str
    title: str
    texture: str
    window: tuple[float, float, float, float]


SAMPLES = (
    Sample("1_mexico_dia.jpg", "México de día", "day", (-118.5, 33.0, -86.5, 14.0)),
    Sample("2_cdmx_noche.jpg", "Valle de México de noche", "night", (-100.2, 20.2, -98.2, 18.8)),
    Sample(
        "3_golfo_noche.jpg",
        "Golfo de México y océano de noche",
        "night",
        (-99.0, 31.0, -80.0, 17.0),
    ),
    Sample(
        "4_jalisco_noche.jpg",
        "Jalisco de noche, detalle máximo",
        "night",
        (-105.8, 22.8, -101.4, 18.9),
    ),
    # Centro galáctico (AR 17h46m, Dec −29°): en el mapa la AR crece a la
    # izquierda desde el centro (0h), así que cae al 76 % del ancho.
    Sample(
        "5_via_lactea.jpg",
        "Vía Láctea hacia el centro galáctico",
        "stars",
        (0.68, 0.56, 0.84, 0.76),
    ),
)


def download(source: Source, raw_dir: Path) -> Path:
    """Descarga una imagen si no está ya, con reintentos (ver ``descarga``).

    Args:
        source: Imagen.
        raw_dir: Carpeta de trabajo para las descargas.

    Returns:
        La ruta del archivo.

    Raises:
        GeodataDownloadError: Si falla después de los reintentos o llega vacía.
    """
    target = raw_dir / source.filename
    if target.exists() and target.stat().st_size > 0:
        logger.info(f"{source.filename}: ya estaba descargado")
        return target
    raw_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")

    def fetch() -> None:
        request = urllib.request.Request(source.url, headers={"User-Agent": "monitor-noticias"})  # noqa: S310 — URL fija de la NASA, siempre https
        with (
            urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response,  # noqa: S310 — misma URL fija
            partial.open("wb") as handle,
        ):
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)

    started = time.perf_counter()
    _with_retries(f"Descarga de {source.url}", fetch)
    if partial.stat().st_size == 0:
        raise GeodataDownloadError(f"{source.url} llegó vacío.")
    partial.replace(target)
    megabytes = target.stat().st_size / 1024 / 1024
    logger.info(f"{source.filename}: {megabytes:,.1f} MB en {time.perf_counter() - started:.0f} s")
    return target


def georeference_command(source: Path, output: Path, size: tuple[int, int] | None) -> list[str]:
    """Comando que da coordenadas a una imagen equirectangular del mundo.

    Args:
        source: JPG de la NASA.
        output: GeoTIFF de salida.
        size: Ancho y alto a los que se lleva (la noche se iguala al día).

    Returns:
        El comando de ``gdal_translate``.
    """
    command = ["gdal_translate", "-q", "-a_srs", "EPSG:4326", "-a_ullr", *WORLD_ULLR]
    if size is not None:
        command += ["-outsize", str(size[0]), str(size[1]), "-r", "bilinear"]
    return [*command, "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", str(source), str(output)]


def night_command(day: Path, lights: Path, output: Path) -> list[str]:
    """Comando que mezcla la noche: Tierra oscurecida con tinte azul más las luces.

    Args:
        day: GeoTIFF de la Tierra de día.
        lights: GeoTIFF de las luces, del mismo tamaño.
        output: GeoTIFF de salida.

    Returns:
        El comando de ``gdal_calc.py`` (una expresión por banda RGB).
    """
    # Una entrada por banda: A, B y C son rojo, verde y azul del día; D, E y F
    # los de las luces. Cada --calc produce una banda de la salida, así cada
    # color lleva su propio factor (el tinte azul).
    command = ["gdal_calc.py", "--quiet"]
    for band, (day_letter, light_letter) in enumerate(zip("ABC", "DEF", strict=True), start=1):
        command += [f"-{day_letter}", str(day), f"--{day_letter}_band={band}"]
        command += [f"-{light_letter}", str(lights), f"--{light_letter}_band={band}"]
    for (day_letter, light_letter), factor in zip(
        zip("ABC", "DEF", strict=True), NIGHT_DAY_FACTORS, strict=True
    ):
        expression = f"numpy.clip({day_letter}*{factor}+{light_letter}*{NIGHT_LIGHT_GAIN},0,255)"
        command += ["--calc", expression]
    return [
        *command,
        # Repetir el comando reemplaza la noche anterior (por ejemplo, la de --muestra).
        "--overwrite",
        "--type=Byte",
        "--co",
        "TILED=YES",
        "--co",
        "COMPRESS=DEFLATE",
        "--outfile",
        str(output),
    ]


def mercator_command(source: Path, output: Path) -> list[str]:
    """Comando que reproyecta a Web Mercator (lo que piden las teselas).

    Args:
        source: GeoTIFF en grados.
        output: GeoTIFF en EPSG:3857.

    Returns:
        El comando de ``gdalwarp``.
    """
    return [
        "gdalwarp",
        "-q",
        "-t_srs",
        "EPSG:3857",
        "-te",
        *MERCATOR_BOUNDS,
        "-r",
        "bilinear",
        "-co",
        "TILED=YES",
        "-co",
        "COMPRESS=DEFLATE",
        "-overwrite",
        str(source),
        str(output),
    ]


def mbtiles_commands(source: Path, output: Path, name: str) -> list[list[str]]:
    """Comandos que cortan las teselas WebP de zoom 0 a ``MAX_ZOOM``.

    Args:
        source: GeoTIFF en EPSG:3857.
        output: Archivo MBTiles.
        name: Nombre para los metadatos.

    Returns:
        ``gdal_translate`` al nivel más detallado y ``gdaladdo`` para los demás.
    """
    return [
        [
            "gdal_translate",
            "-q",
            "-of",
            "MBTILES",
            "-co",
            "TILE_FORMAT=WEBP",
            "-co",
            f"QUALITY={WEBP_QUALITY}",
            # El nivel cuya resolución no supera la de la imagen (no inventa detalle).
            "-co",
            "ZOOM_LEVEL_STRATEGY=LOWER",
            "-co",
            f"NAME={name}",
            "-co",
            f"DESCRIPTION={CREDIT}",
            str(source),
            str(output),
        ],
        ["gdaladdo", "-q", "-r", "average", str(output), *OVERVIEW_FACTORS],
    ]


def sample_command(source: Path, sample: Sample, output: Path, width: int) -> list[str]:
    """Comando que recorta una muestra JPG.

    Args:
        source: GeoTIFF de la textura, o JPG de estrellas.
        sample: Recorte.
        output: JPG de salida.
        width: Ancho del JPG en píxeles.

    Returns:
        El comando de ``gdal_translate``.
    """
    if sample.texture == "stars":
        left, top, right, bottom = sample.window
        window = [
            "-srcwin",
            str(int(left * STARS_8K_WIDTH)),
            str(int(top * STARS_8K_HEIGHT)),
            str(int((right - left) * STARS_8K_WIDTH)),
            str(int((bottom - top) * STARS_8K_HEIGHT)),
        ]
    else:
        window = ["-projwin", *(str(v) for v in sample.window)]
    return [
        "gdal_translate",
        "-q",
        "-of",
        "JPEG",
        "-co",
        "QUALITY=90",
        *window,
        "-outsize",
        str(width),
        "0",
        "-r",
        "bilinear",
        str(source),
        str(output),
    ]


STARS_8K_WIDTH, STARS_8K_HEIGHT = 8192, 4096
# Ancho de las muestras: suficiente para verlas bien en la pantalla.
SAMPLE_WIDTH = 1200


@dataclass(frozen=True, slots=True)
class OutputFile:
    """Un archivo generado, para el manifiesto.

    Attributes:
        name: Ruta relativa a ``geodata/output``.
        size: Bytes.
        sha256: Huella.
    """

    name: str
    size: int
    sha256: str


Runner = Callable[[list[str]], str]


def prepare_textures(
    raw: dict[str, Path], work: Path, runner: Runner = run_tool
) -> dict[str, Path]:
    """Georreferencia el día y las luces y mezcla la noche.

    Args:
        raw: Descargas por ``key``.
        work: Carpeta de trabajo.
        runner: Ejecuta herramientas externas (las pruebas lo reemplazan).

    Returns:
        GeoTIFF en grados de ``day`` y ``night``.
    """
    day = work / "earth_day_4326.tif"
    lights = work / "earth_lights_4326.tif"
    night = work / "earth_night_4326.tif"
    runner(georeference_command(raw[BLUE_MARBLE.key], day, None))
    runner(georeference_command(raw[BLACK_MARBLE.key], lights, (DAY_WIDTH, DAY_HEIGHT)))
    runner(night_command(day, lights, night))
    return {"day": day, "night": night}


def build_tiles(
    textures: dict[str, Path], work: Path, output_dir: Path, runner: Runner = run_tool
) -> list[OutputFile]:
    """Corta, verifica y publica las teselas de día y de noche.

    Args:
        textures: GeoTIFF en grados por nombre (``day``, ``night``).
        work: Carpeta de trabajo.
        output_dir: ``geodata/output``.
        runner: Ejecuta herramientas externas.

    Returns:
        Los PMTiles publicados.
    """
    published = []
    for name, source in textures.items():
        heading(logger, f"earth_{name}.pmtiles (zoom 0–{MAX_ZOOM})")
        mercator = work / f"earth_{name}_3857.tif"
        mbtiles = work / f"earth_{name}.mbtiles"
        pmtiles = work / f"earth_{name}.pmtiles"
        for stale in (mbtiles, pmtiles):
            stale.unlink(missing_ok=True)
        runner(mercator_command(source, mercator))
        for command in mbtiles_commands(mercator, mbtiles, f"earth_{name}"):
            runner(command)
        runner([str(PMTILES_BIN), "convert", str(mbtiles), str(pmtiles)])
        runner([str(PMTILES_BIN), "verify", str(pmtiles)])
        final = output_dir / pmtiles.name
        copy_verified(pmtiles, final)
        size = final.stat().st_size
        logger.info(f"{final.name}: {size / 1024 / 1024:,.1f} MB, verificado")
        published.append(OutputFile(final.name, size, sha256_file(final)))
    return published


def publish_stars(raw: dict[str, Path], output_dir: Path) -> list[OutputFile]:
    """Copia los mapas de estrellas a ``output/space``.

    Args:
        raw: Descargas por ``key``.
        output_dir: ``geodata/output``.

    Returns:
        Los archivos publicados.
    """
    published = []
    for source in (STARS_4K, STARS_8K):
        final = output_dir / SPACE_DIR_NAME / source.filename
        copy_verified(raw[source.key], final)
        published.append(
            OutputFile(f"{SPACE_DIR_NAME}/{final.name}", final.stat().st_size, sha256_file(final))
        )
    return published


def make_samples(
    raw: dict[str, Path], textures: dict[str, Path], output_dir: Path, runner: Runner = run_tool
) -> list[Path]:
    """Genera los 5 recortes para revisar a mano.

    Args:
        raw: Descargas por ``key``.
        textures: GeoTIFF de ``day`` y ``night``.
        output_dir: Carpeta de las muestras.
        runner: Ejecuta herramientas externas.

    Returns:
        Los JPG generados.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for sample in SAMPLES:
        source = raw[STARS_8K.key] if sample.texture == "stars" else textures[sample.texture]
        target = output_dir / sample.name
        runner(sample_command(source, sample, target, SAMPLE_WIDTH))
        logger.info(f"{sample.name}: {sample.title}")
        made.append(target)
    return made


def run(
    work_dir: Path,
    output_dir: Path,
    *,
    samples_only: bool,
    fetch: Callable[[Source, Path], Path] = download,
    runner: Runner = run_tool,
) -> dict[str, object]:
    """Flujo completo (o solo las muestras).

    Args:
        work_dir: Carpeta de trabajo en el disco de Linux.
        output_dir: ``geodata/output``.
        samples_only: Solo descargar y generar las muestras.
        fetch: Descarga una imagen (las pruebas la reemplazan).
        runner: Ejecuta herramientas externas (las pruebas lo reemplazan).

    Returns:
        El manifiesto (vacío de archivos si solo hubo muestras).
    """
    work = work_dir / "tierra"
    heading(logger, "Descargas de la NASA")
    raw = {source.key: fetch(source, work / "raw") for source in SOURCES}
    downloads = [
        {**asdict(s), "sha256": sha256_file(raw[s.key]), "size": raw[s.key].stat().st_size}
        for s in SOURCES
    ]
    heading(logger, "Georreferencia y mezcla de la noche")
    textures = prepare_textures(raw, work, runner)
    if samples_only:
        heading(logger, "Muestras para revisar (no se cortaron teselas)")
        make_samples(raw, textures, output_dir / SAMPLES_DIR_NAME, runner)
        return {"downloads": downloads, "files": []}
    files = build_tiles(textures, work, output_dir, runner) + publish_stars(raw, output_dir)
    manifest: dict[str, object] = {
        "credit": CREDIT,
        "license": LICENSE,
        "max_zoom": MAX_ZOOM,
        "night_day_factors": list(NIGHT_DAY_FACTORS),
        "night_light_gain": NIGHT_LIGHT_GAIN,
        "downloads": downloads,
        "files": [asdict(f) for f in files],
        "generated_at": utc_now_iso(),
    }
    (output_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    parser = argparse.ArgumentParser(description="Texturas de la Tierra y del espacio (NASA).")
    parser.add_argument(
        "--muestra", action="store_true", help="solo 5 recortes para revisar, sin teselas"
    )
    args = parser.parse_args(argv)
    configure_cli_logging()
    run(get_settings().geodata_work_dir, OUTPUT_DIR, samples_only=args.muestra)
    heading(logger, "Listo")


if __name__ == "__main__":
    main()
