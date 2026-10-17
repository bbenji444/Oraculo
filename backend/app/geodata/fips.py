"""Equivalencias de estados de México: código FIPS (GDELT) → clave INEGI.

GDELT ubica las notas con códigos FIPS 10-4 (``MX09``), que **no** coinciden
con las claves INEGI en cuatro estados: Coahuila (FIPS 07 / INEGI 05),
Chiapas (05/07), Chihuahua (06/08) y Colima (08/06). La lista vive en
``geodata/fips_inegi.csv``; su columna ``verificado`` dice si el código se
confirmó con datos reales de GDELT o viene de la norma (ADR-0013).

Lo usan la ingesta de GDELT (para guardar en qué estado ubicó GDELT una
nota) y el proveedor ``indice_local``.

No hace: no usa los nombres de estado de GDELT, que llegan con acentos
dañados ("MéCo" por "México"): solo los códigos.
"""

import csv
from pathlib import Path

from app.geodata.fuentes import REPO_ROOT

FIPS_INEGI_PATH = REPO_ROOT / "geodata" / "fips_inegi.csv"
# México tiene 32 entidades federativas (especificación §12).
STATE_COUNT = 32


class FipsTableError(ValueError):
    """La tabla de equivalencias está incompleta o repetida."""


def read_fips_to_inegi(path: Path = FIPS_INEGI_PATH) -> dict[str, str]:
    """Lee la tabla de equivalencias.

    Args:
        path: CSV con columnas ``fips``, ``inegi``, ``estado`` y ``verificado``.

    Returns:
        Clave INEGI de cada código FIPS (``{"MX07": "05", ...}``).

    Raises:
        FipsTableError: Si no hay exactamente 32 estados distintos de ida y
            de vuelta.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    mapping = {row["fips"].strip(): row["inegi"].strip() for row in rows}
    if len(rows) != STATE_COUNT or len(mapping) != STATE_COUNT:
        raise FipsTableError(f"Se esperaban {STATE_COUNT} códigos FIPS distintos.")
    if len(set(mapping.values())) != STATE_COUNT:
        raise FipsTableError(f"Se esperaban {STATE_COUNT} claves INEGI distintas.")
    return mapping
