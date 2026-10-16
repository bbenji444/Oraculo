"""Comando ``make geo-basemap``: descarga el mapa base de Protomaps, autoalojado.

Recorta de la construcción diaria de Protomaps (OpenStreetMap, 139 GB) dos
archivos PMTiles, más las fuentes y el sprite del estilo, para que el mapa
no dependa de ningún servidor externo (ADR-0004):

- ``basemap_world.pmtiles``: el mundo hasta zoom 6 (≈45 MB).
- ``basemap_mexico.pmtiles``: México y sus islas hasta zoom 14, todas las
  calles (≈1.3 GB). Zoom elegido por Benji el 2026-10-15 tras medir los
  tamaños con ``pmtiles extract --dry-run``.
- ``basemap-assets/``: fuentes Noto Sans (Regular, Medium, Italic) y el
  sprite ``dark`` de ``protomaps/basemaps-assets``.

Todo se descarga a la carpeta de trabajo en el disco de Linux, se verifica
(``pmtiles verify`` y SHA-256) y se copia a ``geodata/output``. Queda un
``MAPA_BASE.json`` con versiones, zooms, tamaños y huellas. Si ya está todo
con los mismos parámetros, no se vuelve a descargar.

Uso: ``python -m app.geodata.mapa_base``

No hace: no genera las capas de INEGI (eso es ``generar_pmtiles``).
"""

import argparse
import hashlib
import io
import json
import logging
import time
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.geodata.carga import copy_verified
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.descarga import WholeFetcher, http_fetch_whole, sha256_file, utc_now_iso
from app.geodata.fuentes import REPO_ROOT
from app.geodata.teselas import PMTILES_BIN, run_tool

logger = logging.getLogger(__name__)

OUTPUT_DIR = REPO_ROOT / "geodata" / "output"
MANIFEST_NAME = "MAPA_BASE.json"

# Construcción diaria de Protomaps fijada (verificada en
# https://build-metadata.protomaps.dev/builds.json el 2026-10-15, versión 4.15.2).
PROTOMAPS_BUILD = "20261015"
PROTOMAPS_URL = f"https://build.protomaps.com/{PROTOMAPS_BUILD}.pmtiles"
WORLD_MAX_ZOOM = 6
# Rectángulo que cubre México con sus islas (Guadalupe llega a -118.3; el
# Arrecife Alacranes y Cozumel, al este; Chiapas, al sur).
MEXICO_BBOX = (-118.6, 14.3, -86.5, 32.9)
MEXICO_MAX_ZOOM = 14
# Hilos de descarga de pmtiles extract (el valor por defecto de la herramienta).
DOWNLOAD_THREADS = 4

# Recursos del estilo (fuentes y sprites) en una versión fija.
ASSETS_COMMIT = "028c18f713baecad011301ff7a69acc39bcc2ae7"
ASSETS_URL = f"https://codeload.github.com/protomaps/basemaps-assets/zip/{ASSETS_COMMIT}"
# Fuentes que usa el estilo de @protomaps/basemaps 5.7.2 (verificado con layers()).
FONTSTACKS = ("Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic")
SPRITE_FLAVOR = "dark"
ASSETS_DIR_NAME = "basemap-assets"
ATTRIBUTION = "© colaboradores de OpenStreetMap (ODbL) · Protomaps"


@dataclass(frozen=True, slots=True)
class Extract:
    """Un recorte del mapa base.

    Attributes:
        name: Nombre del archivo de salida.
        max_zoom: Zoom máximo incluido.
        bbox: Rectángulo (oeste, sur, este, norte) o ``None`` para el mundo.
    """

    name: str
    max_zoom: int
    bbox: tuple[float, float, float, float] | None


EXTRACTS = (
    Extract("basemap_world.pmtiles", WORLD_MAX_ZOOM, None),
    Extract("basemap_mexico.pmtiles", MEXICO_MAX_ZOOM, MEXICO_BBOX),
)


def build_extract_command(extract: Extract, output: Path) -> list[str]:
    """Arma el comando ``pmtiles extract`` de un recorte.

    Args:
        extract: Recorte a descargar.
        output: Archivo de salida.

    Returns:
        El comando como lista de argumentos.
    """
    command = [
        str(PMTILES_BIN),
        "extract",
        PROTOMAPS_URL,
        str(output),
        f"--maxzoom={extract.max_zoom}",
        f"--download-threads={DOWNLOAD_THREADS}",
    ]
    if extract.bbox is not None:
        command.append("--bbox=" + ",".join(str(v) for v in extract.bbox))
    return command


def extract_assets(zip_bytes: bytes, destination: Path) -> list[Path]:
    """Extrae del ZIP de basemaps-assets solo las fuentes y el sprite que se usan.

    Args:
        zip_bytes: Contenido del ZIP descargado.
        destination: Carpeta ``basemap-assets``.

    Returns:
        Archivos extraídos (``zipfile`` verifica el CRC de cada uno).
    """
    wanted_prefixes = tuple(f"fonts/{stack}/" for stack in FONTSTACKS)
    wanted_files = {
        f"sprites/v4/{SPRITE_FLAVOR}{suffix}" for suffix in (".json", ".png", "@2x.json", "@2x.png")
    } | {"fonts/OFL.txt"}
    extracted: list[Path] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            # GitHub agrega una carpeta raíz "basemaps-assets-<commit>/".
            _, _, relative = info.filename.partition("/")
            if info.is_dir() or not (
                relative in wanted_files or relative.startswith(wanted_prefixes)
            ):
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
            extracted.append(target)
    return extracted


@dataclass(frozen=True, slots=True)
class BasemapFile:
    """Registro de un archivo del mapa base en el manifiesto.

    Attributes:
        name: Nombre del archivo.
        max_zoom: Zoom máximo.
        bbox: Rectángulo o ``None`` (mundo).
        size: Bytes.
        sha256: Huella del archivo.
    """

    name: str
    max_zoom: int
    bbox: tuple[float, float, float, float] | None
    size: int
    sha256: str


def _manifest_matches(manifest: Mapping[str, Any], extract: Extract, output_dir: Path) -> bool:
    """Indica si el recorte ya está descargado con los mismos parámetros."""
    if manifest.get("protomaps_build") != PROTOMAPS_BUILD:
        return False
    files = manifest.get("files")
    if not isinstance(files, list):
        return False
    for entry in files:
        if entry.get("name") != extract.name:
            continue
        same_params = entry.get("max_zoom") == extract.max_zoom and (
            entry.get("bbox") == (list(extract.bbox) if extract.bbox else None)
        )
        path = output_dir / extract.name
        return same_params and path.exists() and sha256_file(path) == entry.get("sha256")
    return False


def run(
    work_dir: Path, output_dir: Path, fetch_whole: WholeFetcher = http_fetch_whole
) -> dict[str, object]:
    """Descarga, verifica y publica el mapa base y sus recursos.

    Args:
        work_dir: Carpeta de trabajo en el disco de Linux.
        output_dir: Carpeta servida por nginx (``geodata/output``).
        fetch_whole: Función para descargar el ZIP de recursos (inyectable).

    Returns:
        El manifiesto guardado en ``MAPA_BASE.json``.
    """
    manifest_path = output_dir / MANIFEST_NAME
    previous: dict[str, object] = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    stage_dir = work_dir / "mapa_base"
    stage_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    files: list[BasemapFile] = []
    for extract in EXTRACTS:
        zoom = f"zoom 0–{extract.max_zoom}"
        heading(logger, f"{extract.name} ({'mundo' if extract.bbox is None else 'México'}, {zoom})")
        final = output_dir / extract.name
        if _manifest_matches(previous, extract, output_dir):
            logger.info("Ya estaba descargado con los mismos parámetros; no se vuelve a bajar")
        else:
            staged = stage_dir / extract.name
            started = time.perf_counter()
            run_tool(build_extract_command(extract, staged))
            run_tool([str(PMTILES_BIN), "verify", str(staged)])
            copy_verified(staged, final)
            staged.unlink()
            logger.info(f"Descargado y verificado en {time.perf_counter() - started:.0f} s")
        files.append(
            BasemapFile(
                extract.name,
                extract.max_zoom,
                extract.bbox,
                final.stat().st_size,
                sha256_file(final),
            )
        )
        logger.info(f"{final.stat().st_size / 1024 / 1024:,.1f} MB")

    heading(logger, f"Fuentes y sprite (basemaps-assets {ASSETS_COMMIT[:7]})")
    assets_zip = fetch_whole(ASSETS_URL)
    extracted = extract_assets(assets_zip, output_dir / ASSETS_DIR_NAME)
    logger.info(f"{len(extracted)} archivos en {ASSETS_DIR_NAME}/ ({', '.join(FONTSTACKS)})")

    manifest: dict[str, object] = {
        "protomaps_build": PROTOMAPS_BUILD,
        "source": PROTOMAPS_URL,
        "attribution": ATTRIBUTION,
        "license": "ODbL 1.0 (datos de OpenStreetMap); fuentes Noto bajo OFL 1.1",
        "files": [asdict(f) for f in files],
        "assets_commit": ASSETS_COMMIT,
        "assets_zip_sha256": hashlib.sha256(assets_zip).hexdigest(),
        "generated_at": utc_now_iso(),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    argparse.ArgumentParser(description="Descarga el mapa base de Protomaps.").parse_args(argv)
    configure_cli_logging()
    run(get_settings().geodata_work_dir, OUTPUT_DIR)
    heading(logger, f"Listo. Manifiesto en {OUTPUT_DIR / MANIFEST_NAME}")


if __name__ == "__main__":
    main()
