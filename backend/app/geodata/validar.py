"""Comando ``make geo-validate``: criterios de aceptación del catálogo (§12).

Imprime cada revisión con lo esperado y lo obtenido, y termina con código
de salida 1 si alguna falla, para que ``make geo-load`` se detenga antes de
generar mapas a partir de datos incorrectos.

Uso: ``python -m app.geodata.validar``

No hace: no corrige datos.
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from typing import Any

from sqlalchemy import create_engine

from app.core.config import get_settings
from app.geodata.cargar import read_inspection
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.fuentes import INEGI_WORK_SUBDIR, INSPECTION_PATH
from app.geodata.inspeccion import ExtractionPlan, read_catalog
from app.geodata.validacion import CheckResult, Expectations, run_checks

logger = logging.getLogger(__name__)

# Especificación §12: 32 entidades, 16 alcaldías en la CDMX y 5 nombres con Ñ.
STATE_COUNT = 32
CDMX_MUNICIPALITY_COUNT = 16
MIN_ENIE_NAMES = 5


def build_expectations(inspection: dict[str, Any], catalog: dict[str, str]) -> Expectations:
    """Arma los valores esperados a partir de la inspección y del catálogo.

    Args:
        inspection: Contenido de ``INSPECCION.json``.
        catalog: Municipios del catálogo oficial (clave → nombre).

    Returns:
        Los valores esperados.
    """
    return Expectations(
        state_count=STATE_COUNT,
        cdmx_municipality_count=CDMX_MUNICIPALITY_COUNT,
        catalog_municipalities=catalog,
        locality_count=inspection["localities"]["distinct"],
        locality_polygon_count=inspection["localities"]["polygons"],
        min_enie_names=MIN_ENIE_NAMES,
    )


def report(results: Sequence[CheckResult]) -> bool:
    """Muestra los resultados.

    Args:
        results: Resultados de ``run_checks``.

    Returns:
        ``True`` si todas las revisiones pasaron.
    """
    for result in results:
        line = f"{result.name}: {result.actual} (esperado {result.expected})"
        if result.passed:
            logger.info(line)
        else:
            logger.error(line)
    passed = all(r.passed for r in results)
    heading(logger, "Todas las revisiones pasaron" if passed else "HAY REVISIONES QUE FALLARON")
    return passed


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    argparse.ArgumentParser(description="Valida el catálogo geográfico.").parse_args(argv)
    configure_cli_logging()
    settings = get_settings()
    catalog_path = (
        settings.geodata_work_dir
        / INEGI_WORK_SUBDIR
        / ExtractionPlan((), "", (), "municipales.csv").catalog_relative_path
    )
    catalog, _ = read_catalog(catalog_path)
    expectations = build_expectations(read_inspection(INSPECTION_PATH), catalog)
    heading(logger, "Validando el catálogo geográfico (especificación §12)")
    engine = create_engine(settings.database_url())
    try:
        with engine.connect() as conn:
            results = run_checks(conn, expectations)
    finally:
        engine.dispose()
    if not report(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
