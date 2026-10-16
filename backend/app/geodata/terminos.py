"""Términos de búsqueda de cada lugar y códigos de país (ADR-0009).

Dos datos que no cambian la geometría del catálogo, pero sí cómo se arma
una consulta de noticias:

- ``search_terms``: con qué palabras se busca un lugar en los proveedores.
  Sale de la lista curada ``geodata/search_terms.csv``. Las regiones que no
  están en la lista quedan vacías y se buscan por su ``name``.
- ``iso_a2``, ``fips_code`` y ``name_en`` de cada país: los filtros por
  país de cada proveedor, tomados de la tabla de atributos de Natural Earth.

Lo usan ``make geo-terms`` (``aplicar_terminos``) y el final de la carga
completa (``carga.run_load``), así que hay una sola forma de llenarlos.

No hace: no carga geometrías ni toca ``aliases`` (esos son para reconocer
lugares en el texto de las notas, F4).
"""

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, text

from app.geodata.dbf import iter_raw_values

# Natural Earth pone -99 cuando un código no aplica (ADR-0008).
NE_MISSING = "-99"
# ISO_A2_EH ("EH": siempre lleno) en lugar de ISO_A2, que vale -99 en
# Francia y Noruega; FIPS_10 es el código que entiende GDELT.
NE_CODE_FIELDS = ("ADM0_A3", "ISO_A3", "ISO_A2_EH", "FIPS_10", "NAME_EN")
_TWO_LETTERS = re.compile(r"^[A-Z]{2}$")


class SearchTermsError(Exception):
    """La lista de términos o los códigos de país no se pueden aplicar."""


@dataclass(frozen=True, slots=True)
class CountryCodes:
    """Códigos de un país para filtrar en los proveedores.

    Attributes:
        code: Clave del país en ``regions`` (ISO-A3 o ADM0_A3, ADR-0008).
        iso_a2: Código ISO de 2 letras (SearchApi, Google News RSS).
        fips_code: Código FIPS de 2 letras (GDELT), o ``None`` si no tiene.
        name_en: Nombre en inglés (respaldo de GDELT sin FIPS).
    """

    code: str
    iso_a2: str | None
    fips_code: str | None
    name_en: str


def read_search_terms(path: Path) -> dict[str, list[str]]:
    """Lee la lista curada de términos de búsqueda.

    Args:
        path: CSV con columnas ``code``, ``termino`` y ``nota``.

    Returns:
        Términos por clave de región, sin repetir y en el orden del archivo
        (el orden importa: el primero es el que se muestra primero).

    Raises:
        SearchTermsError: Si un término está vacío.
    """
    terms: dict[str, list[str]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            term = " ".join(row["termino"].split())
            if not term:
                raise SearchTermsError(f"{path.name}, línea {line}: el término está vacío.")
            code = row["code"].strip()
            if term not in terms[code]:
                terms[code].append(term)
    return dict(terms)


def _two_letters(value: str) -> str | None:
    """Devuelve el código si son 2 letras mayúsculas; ``None`` si es -99 o vacío."""
    value = value.strip()
    return value if _TWO_LETTERS.match(value) else None


def _read_records(path: Path, encoding: str) -> list[dict[str, str]]:
    """Lee los campos de códigos de un shapefile (su .dbf) o de un GeoJSON."""
    if path.suffix.lower() in (".geojson", ".json"):
        features = json.loads(path.read_text(encoding="utf-8"))["features"]
        return [
            {f: str(feat["properties"].get(f, "")) for f in NE_CODE_FIELDS} for feat in features
        ]
    dbf = path.with_suffix(".dbf")
    return [
        {f: v.decode(encoding) for f, v in zip(NE_CODE_FIELDS, values, strict=True)}
        for values in iter_raw_values(dbf, NE_CODE_FIELDS)
    ]


def read_country_codes(path: Path, encoding: str = "utf-8") -> list[CountryCodes]:
    """Lee los códigos de país de la capa de Natural Earth.

    La clave de cada país se calcula con la misma regla del cargador
    (``carga.load_countries``, ADR-0008): ``ISO_A3`` si es válido y único,
    y si no, ``ADM0_A3``.

    Args:
        path: El ``.shp`` de Natural Earth (se lee su ``.dbf``) o un GeoJSON
            con los mismos campos (pruebas).
        encoding: Encoding de los textos del DBF.

    Returns:
        Un registro por país.
    """
    records = _read_records(path, encoding)
    iso_counts = Counter(r["ISO_A3"] for r in records)
    countries = []
    for r in records:
        iso_a3 = r["ISO_A3"].strip()
        unique_iso = iso_a3 != NE_MISSING and iso_counts[iso_a3] == 1
        countries.append(
            CountryCodes(
                code=iso_a3 if unique_iso else r["ADM0_A3"].strip(),
                iso_a2=_two_letters(r["ISO_A2_EH"]),
                fips_code=_two_letters(r["FIPS_10"]),
                name_en=r["NAME_EN"].strip(),
            )
        )
    return countries


def apply_search_terms(engine: Engine, terms: dict[str, list[str]]) -> int:
    """Reemplaza los términos de búsqueda con los de la lista curada.

    Las regiones que ya no están en la lista vuelven a quedar vacías, para
    que borrar una línea del CSV tenga efecto.

    Args:
        engine: Conexión a la base.
        terms: Términos por clave de región.

    Returns:
        Número de regiones con términos.

    Raises:
        SearchTermsError: Si alguna clave no existe en ``regions``.
    """
    with engine.begin() as conn:
        existing = set(
            conn.execute(
                text("SELECT code FROM regions WHERE code = ANY(:codes)"), {"codes": list(terms)}
            ).scalars()
        )
        unknown = sorted(set(terms) - existing)
        if unknown:
            raise SearchTermsError(f"Términos con claves inexistentes: {', '.join(unknown)}")
        conn.execute(
            text("UPDATE regions SET search_terms = '{}' WHERE cardinality(search_terms) > 0")
        )
        for code, values in terms.items():
            conn.execute(
                text("UPDATE regions SET search_terms = :t WHERE code = :code"),
                {"t": values, "code": code},
            )
    return len(terms)


def apply_country_codes(engine: Engine, countries: list[CountryCodes]) -> int:
    """Guarda los códigos de cada país en ``regions``.

    Args:
        engine: Conexión a la base.
        countries: Códigos leídos de Natural Earth.

    Returns:
        Número de países actualizados.

    Raises:
        SearchTermsError: Si un país de Natural Earth no está en ``regions``
            (señal de que la carga y esta lectura no usan la misma regla).
    """
    with engine.begin() as conn:
        updated = 0
        missing = []
        for country in countries:
            result = conn.execute(
                text(
                    "UPDATE regions SET iso_a2 = :iso_a2, fips_code = :fips, name_en = :name_en "
                    "WHERE code = :code AND level = 'country'"
                ),
                {
                    "iso_a2": country.iso_a2,
                    "fips": country.fips_code,
                    "name_en": country.name_en,
                    "code": country.code,
                },
            )
            if result.rowcount == 0:
                missing.append(country.code)
            updated += result.rowcount
        if missing:
            raise SearchTermsError(f"Países sin región cargada: {', '.join(sorted(missing))}")
    return updated
