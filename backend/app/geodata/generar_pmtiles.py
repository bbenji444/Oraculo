"""Comando ``make geo-tiles``: genera los PMTiles de países, estados, municipios y localidades.

Lee de la tabla ``regions`` (ya cargada y validada) y deja un archivo por
capa en ``geodata/output/``, que nginx sirve en ``/tiles/`` con soporte de
peticiones Range (ADR-0004).

Uso: ``python -m app.geodata.generar_pmtiles``

No hace: no genera el mapa base de Protomaps (eso es ``make geo-basemap``).
"""

import argparse
import logging
import time
from collections.abc import Sequence

from app.core.config import get_settings
from app.geodata.cargar import target_from_settings
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.fuentes import REPO_ROOT
from app.geodata.teselas import LAYERS, generate_layer, show_header

logger = logging.getLogger(__name__)

OUTPUT_DIR = REPO_ROOT / "geodata" / "output"
_BYTES_PER_MB = 1024 * 1024
# Líneas de `pmtiles show` que vale la pena mostrar a una persona.
_HEADER_KEYS = ("min zoom", "max zoom", "bounds", "tile type", "addressed tiles count")


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    argparse.ArgumentParser(description="Genera los PMTiles de las capas.").parse_args(argv)
    configure_cli_logging()
    settings = get_settings()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = target_from_settings(settings)
    for layer in LAYERS:
        heading(logger, f"{layer.description}: zoom {layer.min_zoom}–{layer.max_zoom}")
        started = time.perf_counter()
        result = generate_layer(layer, target, settings.geodata_work_dir, OUTPUT_DIR)
        logger.info(
            f"{result.path.name}: {result.size_bytes / _BYTES_PER_MB:.1f} MB "
            f"en {time.perf_counter() - started:.0f} s"
        )
        logger.info(f"pmtiles verify: {result.verify_output or 'sin errores'}")
        for line in show_header(result.path).splitlines():
            if line.strip().lower().startswith(_HEADER_KEYS):
                logger.info(line.strip())
    heading(logger, f"Listo. Archivos en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
