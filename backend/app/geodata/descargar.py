"""Comando ``make geo-download``: descarga las fuentes de geodatos.

Baja cada fuente de ``app.geodata.fuentes`` a ``geodata/raw/`` y registra
URL, edición, fecha, tamaño y SHA-256 en ``geodata/raw/MANIFIESTO.json``.
Si un archivo ya está y su SHA-256 coincide con el manifiesto, no lo vuelve
a bajar (idempotente). Con ``--forzar`` descarga todo de nuevo.

Uso: ``python -m app.geodata.descargar [--forzar]``

No hace: no descomprime ni revisa el contenido (eso es ``inspeccionar``).
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from app.geodata import descarga
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.fuentes import ALL_SOURCES, MANIFEST_PATH, RAW_DIR, Source

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024


def download_source(
    source: Source, raw_dir: Path, fetchers: descarga.Fetchers
) -> descarga.ManifestEntry:
    """Descarga una fuente y devuelve su entrada para el manifiesto.

    Args:
        source: Fuente a descargar.
        raw_dir: Carpeta ``geodata/raw``.
        fetchers: Funciones de red a usar.

    Returns:
        La entrada del manifiesto con tamaño y SHA-256.

    Raises:
        descarga.GeodataDownloadError: Si la descarga falla.
    """
    destination = raw_dir / source.relative_path
    if source.member is not None:
        location = descarga.locate_member(source.url, source.member, fetchers.range, fetchers.size)
        logger.info(
            f"'{source.member}' ubicado dentro del ZIP remoto: "
            f"{location.compressed_size / _BYTES_PER_MB:.1f} MB comprimido"
        )
        descarga.download_member(source.url, location, destination, fetchers.range)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(fetchers.whole(source.url))
    return descarga.ManifestEntry(
        key=source.key,
        title=source.title,
        url=source.url,
        member=source.member,
        edition=source.edition,
        license=source.license,
        path=source.relative_path,
        size=destination.stat().st_size,
        sha256=descarga.sha256_file(destination),
        downloaded_at=descarga.utc_now_iso(),
    )


def run(
    sources: Sequence[Source],
    raw_dir: Path,
    manifest_path: Path,
    *,
    force: bool,
    fetchers: descarga.Fetchers | None = None,
) -> dict[str, descarga.ManifestEntry]:
    """Descarga las fuentes que falten o hayan cambiado y actualiza el manifiesto.

    Args:
        sources: Fuentes a revisar.
        raw_dir: Carpeta ``geodata/raw``.
        manifest_path: Ruta de ``MANIFIESTO.json``.
        force: Si es ``True``, descarga aunque ya exista.
        fetchers: Funciones de red; por defecto, las reales (urllib).

    Returns:
        El manifiesto actualizado.
    """
    fetchers = fetchers or descarga.Fetchers()
    manifest = descarga.load_manifest(manifest_path)
    for source in sources:
        heading(logger, source.title)
        if not force and descarga.is_up_to_date(manifest.get(source.key), raw_dir):
            logger.info("Ya estaba descargado y su SHA-256 coincide; no se vuelve a bajar")
            continue
        entry = download_source(source, raw_dir, fetchers)
        manifest[source.key] = entry
        # Se guarda después de cada fuente: si la siguiente falla, esta queda registrada.
        descarga.save_manifest(manifest_path, manifest)
        logger.info(f"{entry.path}: {entry.size / _BYTES_PER_MB:.1f} MB, SHA-256 {entry.sha256}")
    return manifest


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    parser = argparse.ArgumentParser(description="Descarga las fuentes de geodatos.")
    parser.add_argument("--forzar", action="store_true", help="descargar aunque ya exista")
    args = parser.parse_args(argv)
    configure_cli_logging()
    run(ALL_SOURCES, RAW_DIR, MANIFEST_PATH, force=args.forzar)
    heading(logger, f"Listo. Manifiesto en {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
