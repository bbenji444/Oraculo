"""Comando ``make geo-load`` (paso de carga): lleva los geodatos a PostGIS.

Usa las capas que ``make geo-inspect`` extrajo a la carpeta de trabajo y el
encoding que decidió esa inspección (``INSPECCION.json``). Por eso exige que
la inspección se haya corrido antes: es el punto donde una persona revisó
5 nombres reales (CLAUDE.md §2.6).

Uso: ``python -m app.geodata.cargar``

No hace: no descarga ni inspecciona; tampoco valida los criterios de
aceptación (eso es ``validar``).
"""

import argparse
import json
import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from app.core.config import Settings, get_settings
from app.geodata.carga import LayerInput, LoadInputs, LoadSummary, PostgresTarget, run_load
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.fuentes import (
    ALIASES_PATH,
    INEGI_CODE_FIELD,
    INEGI_DATA_DIR,
    INEGI_MG,
    INEGI_NAME_FIELD,
    INEGI_WORK_SUBDIR,
    INSPECTION_PATH,
    NATURAL_EARTH_COUNTRIES,
    NATURAL_EARTH_LAYER,
    NATURAL_EARTH_WORK_SUBDIR,
    SEARCH_TERMS_PATH,
)

logger = logging.getLogger(__name__)

NE_FIELDS = ("ADM0_A3", "ISO_A3", "NAME_ES", "NAME")
_LEVEL_NAMES = {
    "country": "países",
    "state": "estados",
    "municipality": "municipios",
    "locality": "localidades",
}


class MissingInspectionError(Exception):
    """No se ha corrido ``make geo-inspect`` (o faltan las capas extraídas)."""


def build_inputs(inspection: dict[str, Any], work_dir: Path) -> LoadInputs:
    """Arma las entradas del cargador a partir de la inspección.

    Args:
        inspection: Contenido de ``INSPECCION.json``.
        work_dir: Carpeta de trabajo donde la inspección extrajo las capas.

    Returns:
        Las entradas para ``run_load``.

    Raises:
        MissingInspectionError: Si falta alguna capa extraída.
    """
    shp_dir = work_dir / INEGI_WORK_SUBDIR / INEGI_DATA_DIR
    inegi = inspection["inegi"]

    def layer(code: str, table: str, *, is_point: bool = False) -> LayerInput:
        path = shp_dir / f"{code}.shp"
        if not path.exists():
            raise MissingInspectionError(f"Falta {path}. Corre primero: wsl make geo-inspect")
        return LayerInput(
            table, path, inegi[code]["encoding"], is_point, (INEGI_CODE_FIELD, INEGI_NAME_FIELD)
        )

    ne_path = work_dir / NATURAL_EARTH_WORK_SUBDIR / f"{NATURAL_EARTH_LAYER}.shp"
    if not ne_path.exists():
        raise MissingInspectionError(f"Falta {ne_path}. Corre primero: wsl make geo-inspect")
    return LoadInputs(
        countries=LayerInput(
            "ne_countries", ne_path, inspection["natural_earth"]["encoding"], False, NE_FIELDS
        ),
        states=layer("00ent", "inegi_ent"),
        municipalities=layer("00mun", "inegi_mun"),
        locality_points=layer("00lpr", "inegi_lpr", is_point=True),
        locality_polygons=layer("00l", "inegi_l"),
        aliases_csv=ALIASES_PATH,
        search_terms_csv=SEARCH_TERMS_PATH,
        inegi_source=f"INEGI Marco Geoestadístico, edición {INEGI_MG.edition}",
        natural_earth_source=f"Natural Earth 1:10m, {NATURAL_EARTH_COUNTRIES.edition}",
    )


def read_inspection(path: Path) -> dict[str, Any]:
    """Lee ``INSPECCION.json``.

    Args:
        path: Ruta del archivo.

    Returns:
        Su contenido.

    Raises:
        MissingInspectionError: Si no existe.
    """
    if not path.exists():
        raise MissingInspectionError(
            "No existe INSPECCION.json. Corre primero: wsl make geo-inspect"
        )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def target_from_settings(settings: Settings) -> PostgresTarget:
    """Datos de conexión de ``ogr2ogr`` para la base de desarrollo.

    Args:
        settings: Configuración de la aplicación.

    Returns:
        El destino de la carga.
    """
    return PostgresTarget(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )


def report(summary: LoadSummary, seconds: float) -> None:
    """Muestra el resultado de la carga.

    Args:
        summary: Resultado de ``run_load``.
        seconds: Duración total.
    """
    heading(logger, f"Carga terminada en {seconds:.0f} s")
    for level, name in _LEVEL_NAMES.items():
        logger.info(f"{name.capitalize()}: {summary.counts.get(level, 0):,}")
    for table, repaired in summary.repaired.items():
        if repaired:
            logger.warning(f"{table}: {repaired:,} geometrías inválidas reparadas con ST_MakeValid")
    logger.info(f"Alias aplicados: {summary.aliases}")
    logger.info(f"Regiones con términos de búsqueda: {summary.search_terms}")
    logger.info(f"Países con códigos para los proveedores: {summary.country_codes}")


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    argparse.ArgumentParser(description="Carga los geodatos a PostGIS.").parse_args(argv)
    configure_cli_logging()
    settings = get_settings()
    inputs = build_inputs(read_inspection(INSPECTION_PATH), settings.geodata_work_dir)
    engine = create_engine(settings.database_url())
    heading(logger, "Cargando geodatos a PostGIS (puede tardar unos minutos)")
    started = time.perf_counter()
    try:
        summary = run_load(
            engine, target_from_settings(settings), inputs, settings.geodata_work_dir
        )
    finally:
        engine.dispose()
    report(summary, time.perf_counter() - started)


if __name__ == "__main__":
    main()
