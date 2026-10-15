"""Comando ``make geo-inspect``: revisa los geodatos descargados antes de cargarlos.

Extrae del ZIP integrado de INEGI solo las capas que se usan, y para cada una
reporta registros, campos, proyección (EPSG), encoding (con su evidencia) y
claves repetidas. Compara el número de municipios con el catálogo oficial de
la edición, revisa Natural Earth y muestra 5 nombres reales con Ñ y acentos.
Guarda la decisión de encoding y proyección en ``INSPECCION.json``, que usa el
cargador.

Uso: ``python -m app.geodata.inspeccionar``

No hace: no carga nada. CLAUDE.md §2.6 pide que una persona revise los
ejemplos antes de procesar los datos completos.
"""

import argparse
import json
import logging
import zipfile
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from app.geodata import dbf
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.encoding import detect_encoding
from app.geodata.fuentes import (
    INEGI_DATA_DIR,
    INEGI_EXTRACT_DIR,
    INEGI_LAYERS,
    INEGI_MG,
    INEGI_MUNICIPAL_CATALOG_SUFFIX,
    INSPECTION_PATH,
    NATURAL_EARTH_COUNTRIES,
    RAW_DIR,
    SHAPEFILE_PARTS,
)
from app.geodata.inspeccion import (
    ExtractionPlan,
    LayerInspection,
    detect_epsg,
    extract_layers,
    inspect_layer,
    pick_examples,
    read_catalog_codes,
)

logger = logging.getLogger(__name__)

# Número de ejemplos reales que pide CLAUDE.md §2.6 y §6.4.
EXAMPLE_COUNT = 5
# Capas de donde salen los ejemplos: municipios y localidades tienen más Ñ.
_EXAMPLE_LAYERS = ("00mun", "00l", "00lpr")
_NE_DIR_NAME = "ne_10m_admin_0_countries"
# Campos de Natural Earth que usa el cargador (ADR-0008).
NE_FIELDS = ("ADM0_A3", "ISO_A3", "NAME_ES")
# Valor que Natural Earth pone en ISO_A3 cuando no aplica (Francia, Noruega...).
NE_MISSING_ISO = b"-99"


def _report_layer(result: LayerInspection) -> None:
    heading(logger, f"Capa {result.layer}: {result.description}")
    logger.info(f"Registros: {result.record_count:,}")
    logger.info(f"Campos: {', '.join(result.fields)}")
    logger.info(f"Proyección: {result.epsg}")
    enc = result.encoding
    scores = ", ".join(
        f"{s.encoding}={'no decodifica' if not s.decodes else s.score}" for s in enc.scores
    )
    logger.info(f"Encoding elegido: {enc.chosen} (calificaciones: {scores})")
    if enc.agrees_with_declared is False:
        logger.warning(f"El .cpg declara '{enc.declared}', distinto del detectado")
    elif enc.agrees_with_declared:
        logger.info(f"Coincide con lo que declara el .cpg ('{enc.declared}')")
    if result.duplicate_codes:
        logger.warning(f"Claves CVEGEO repetidas: {result.duplicate_codes}")
    else:
        logger.info("Sin claves CVEGEO repetidas")


def inspect_natural_earth(zip_path: Path, destination: Path) -> dict[str, object]:
    """Extrae y revisa la capa de países de Natural Earth.

    Args:
        zip_path: ZIP descargado de Natural Earth.
        destination: Carpeta donde extraerlo.

    Returns:
        Resumen para ``INSPECCION.json``.
    """
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(destination)
    dbf_path = destination / f"{_NE_DIR_NAME}.dbf"
    rows = list(dbf.iter_raw_values(dbf_path, NE_FIELDS))
    cpg = destination / f"{_NE_DIR_NAME}.cpg"
    declared = cpg.read_text(encoding="ascii").strip() if cpg.exists() else None
    report = detect_encoding((name for _, _, name in rows), declared)
    missing_iso = sum(1 for _, iso, _ in rows if iso == NE_MISSING_ISO)
    heading(logger, "Natural Earth: países")
    logger.info(f"Registros: {len(rows)}; campos usados: {', '.join(NE_FIELDS)}")
    logger.info(f"Proyección: {detect_epsg(destination / f'{_NE_DIR_NAME}.prj')}")
    logger.info(f"Encoding: {report.chosen} (.cpg declara '{declared}')")
    logger.info(f"Países con ISO_A3 = -99 (se usará ADM0_A3): {missing_iso}")
    samples = [
        name.decode(report.chosen)
        for adm0, _, name in rows
        if adm0 in {b"MEX", b"USA", b"PER", b"JPN", b"FRA"}
    ]
    logger.info(f"Nombres en español de muestra: {', '.join(sorted(samples))}")
    return {"encoding": report.chosen, "records": len(rows), "missing_iso_a3": missing_iso}


def run(raw_dir: Path, extract_dir: Path, inspection_path: Path) -> dict[str, object]:
    """Ejecuta la inspección completa y guarda ``INSPECCION.json``.

    Args:
        raw_dir: Carpeta ``geodata/raw``.
        extract_dir: Carpeta donde extraer las capas de INEGI.
        inspection_path: Ruta del resultado.

    Returns:
        El contenido guardado en ``INSPECCION.json``.
    """
    heading(logger, "Extrayendo capas del ZIP integrado de INEGI")
    plan = ExtractionPlan(
        layers=tuple(INEGI_LAYERS),
        data_dir=INEGI_DATA_DIR,
        parts=SHAPEFILE_PARTS,
        catalog_suffix=INEGI_MUNICIPAL_CATALOG_SUFFIX,
    )
    extracted = extract_layers(raw_dir / INEGI_MG.relative_path, extract_dir, plan)
    logger.info(f"{len(extracted)} archivos en {extract_dir}")

    shp_dir = extract_dir / INEGI_DATA_DIR
    results = {
        layer: inspect_layer(shp_dir, layer, description)
        for layer, description in INEGI_LAYERS.items()
    }
    for result in results.values():
        _report_layer(result)

    heading(logger, "Catálogo oficial de municipios de la edición")
    catalog_codes, catalog_encoding = read_catalog_codes(extract_dir / plan.catalog_relative_path)
    layer_codes = {
        code.decode("ascii") for (code,) in dbf.iter_raw_values(shp_dir / "00mun.dbf", ("CVEGEO",))
    }
    logger.info(f"Municipios en el catálogo: {len(catalog_codes):,} (encoding {catalog_encoding})")
    missing_in_layer = sorted(catalog_codes - layer_codes)
    extra_in_layer = sorted(layer_codes - catalog_codes)
    if not missing_in_layer and not extra_in_layer:
        logger.info(f"Mismas {len(layer_codes):,} claves que los polígonos de 00mun")
    else:
        logger.warning(f"En el catálogo pero sin polígono: {missing_in_layer or 'ninguno'}")
        logger.warning(f"Con polígono pero fuera del catálogo: {extra_in_layer or 'ninguno'}")

    heading(logger, f"{EXAMPLE_COUNT} nombres reales con Ñ y acentos (para revisión humana)")
    example_rows = [
        (row, results[layer].encoding.chosen)
        for layer in _EXAMPLE_LAYERS
        for row in dbf.iter_raw_values(shp_dir / f"{layer}.dbf", ("CVEGEO", "NOMGEO"))
    ]
    encodings = {enc for _, enc in example_rows}
    examples = pick_examples((row for row, _ in example_rows), encodings.pop(), EXAMPLE_COUNT)
    for number, example in enumerate(examples, start=1):
        logger.info(f"{number}. {example.code}  {example.name}   [bytes: {example.raw_hex}]")

    natural_earth = inspect_natural_earth(
        raw_dir / NATURAL_EARTH_COUNTRIES.relative_path,
        raw_dir / "natural_earth" / _NE_DIR_NAME,
    )

    summary: dict[str, object] = {
        "inegi": {
            layer: {
                "epsg": r.epsg,
                "encoding": r.encoding.chosen,
                "records": r.record_count,
                "duplicate_codes": r.duplicate_codes,
            }
            for layer, r in results.items()
        },
        "inegi_municipal_catalog": {
            "count": len(catalog_codes),
            "missing_in_layer": missing_in_layer,
            "extra_in_layer": extra_in_layer,
        },
        "examples": [asdict(e) for e in examples],
        "natural_earth": natural_earth,
    }
    inspection_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    argparse.ArgumentParser(description="Revisa los geodatos descargados.").parse_args(argv)
    configure_cli_logging()
    run(RAW_DIR, INEGI_EXTRACT_DIR, INSPECTION_PATH)
    heading(logger, f"Listo. Resultado en {INSPECTION_PATH}")


if __name__ == "__main__":
    main()
