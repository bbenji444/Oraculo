"""Comando ``make geo-terms``: términos de búsqueda, alias y códigos de país (ADR-0009).

Aplica ``geodata/search_terms.csv``, los alias de ``geodata/aliases.csv`` (los
usa el geolocalizador, §11) y los códigos de país de Natural Earth
sobre el catálogo ya cargado, sin volver a cargar geometrías (tarda
segundos, no minutos). ``make geo-load`` hace lo mismo al final de la carga
completa, con las mismas funciones (``app.geodata.terminos``).

Uso:
    ``python -m app.geodata.aplicar_terminos --muestra``  (solo muestra)
    ``python -m app.geodata.aplicar_terminos``            (aplica)

Con ``--muestra`` no escribe nada: enseña ejemplos reales de lo que se
aplicaría, para revisarlos antes (CLAUDE.md §2.6).

No hace: no descarga Natural Earth; usa la copia que dejó ``make geo-inspect``
en la carpeta de trabajo.
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings
from app.geodata.carga import apply_aliases, read_aliases
from app.geodata.cargar import MissingInspectionError, read_inspection
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.fuentes import (
    ALIASES_PATH,
    INSPECTION_PATH,
    NATURAL_EARTH_LAYER,
    NATURAL_EARTH_WORK_SUBDIR,
    SEARCH_TERMS_PATH,
)
from app.geodata.terminos import (
    CountryCodes,
    apply_country_codes,
    apply_search_terms,
    read_country_codes,
    read_search_terms,
)

logger = logging.getLogger(__name__)

# Países que se muestran como ejemplo: México y Colombia (historias H1 y H4),
# España (ISO y FIPS distintos), Noruega (sin FIPS) y Estados Unidos.
SAMPLE_COUNTRIES = ("MEX", "COL", "ESP", "NOR", "USA")


def natural_earth_path(work_dir: Path) -> Path:
    """Ruta del shapefile de países que extrajo la inspección.

    Args:
        work_dir: Carpeta de trabajo (``GEODATA_WORK_DIR``).

    Returns:
        La ruta del ``.shp``.

    Raises:
        MissingInspectionError: Si la inspección no lo ha extraído.
    """
    path = work_dir / NATURAL_EARTH_WORK_SUBDIR / f"{NATURAL_EARTH_LAYER}.shp"
    if not path.with_suffix(".dbf").exists():
        raise MissingInspectionError(f"Falta {path}. Corre primero: wsl make geo-inspect")
    return path


def show_terms(engine: Engine, terms: dict[str, list[str]]) -> None:
    """Muestra cada región de la lista con su nombre oficial y sus términos.

    Args:
        engine: Conexión a la base.
        terms: Términos por clave de región.
    """
    with engine.connect() as conn:
        names: dict[str, str] = dict(
            conn.execute(
                text("SELECT code, name FROM regions WHERE code = ANY(:codes)"),
                {"codes": list(terms)},
            ).all()
        )
    for code, values in terms.items():
        logger.info(f"{code} {names.get(code, '¿no existe?')} → {' | '.join(values)}")


def show_countries(countries: Sequence[CountryCodes]) -> None:
    """Muestra los códigos de los países de ejemplo y cuántos no tienen FIPS.

    Args:
        countries: Códigos leídos de Natural Earth.
    """
    by_code = {c.code: c for c in countries}
    for code in SAMPLE_COUNTRIES:
        c = by_code[code]
        logger.info(f"{code} {c.name_en}: ISO-2 {c.iso_a2} · FIPS {c.fips_code or '(sin FIPS)'}")
    without_fips = sum(1 for c in countries if c.fips_code is None)
    without_iso = sum(1 for c in countries if c.iso_a2 is None)
    logger.info(
        f"{len(countries)} países · {without_fips} sin FIPS (GDELT usará su nombre en "
        f"inglés) · {without_iso} sin ISO-2"
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos.

    Args:
        argv: Argumentos (por defecto, los de la línea de comandos).
    """
    parser = argparse.ArgumentParser(description="Aplica términos de búsqueda y códigos de país.")
    parser.add_argument("--muestra", action="store_true", help="solo muestra, no escribe")
    args = parser.parse_args(argv)
    configure_cli_logging()
    settings = get_settings()
    encoding = read_inspection(INSPECTION_PATH)["natural_earth"]["encoding"]
    terms = read_search_terms(SEARCH_TERMS_PATH)
    aliases = read_aliases(ALIASES_PATH)
    countries = read_country_codes(natural_earth_path(settings.geodata_work_dir), encoding)
    engine = create_engine(settings.database_url())
    try:
        mode = "Vista previa (no se escribe nada)" if args.muestra else "Aplicando"
        heading(logger, f"{mode}: términos de búsqueda de {SEARCH_TERMS_PATH.name}")
        show_terms(engine, terms)
        heading(logger, f"{mode}: alias de {ALIASES_PATH.name}")
        show_terms(engine, aliases)
        heading(logger, f"{mode}: códigos de país de Natural Earth")
        show_countries(countries)
        if args.muestra:
            return
        heading(logger, "Guardando en regions")
        logger.info(f"Regiones con términos: {apply_search_terms(engine, terms)}")
        logger.info(f"Alias aplicados: {apply_aliases(engine, aliases)}")
        logger.info(f"Países con códigos: {apply_country_codes(engine, countries)}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
