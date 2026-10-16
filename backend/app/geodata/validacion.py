"""Criterios de aceptación del catálogo geográfico (especificación §12).

Cada revisión consulta la base y devuelve un resultado con lo esperado, lo
obtenido y si pasó. Los valores esperados vienen en ``Expectations`` para
poder probar las mismas revisiones con el mini-catálogo de pruebas.

Criterios de §12, más revisiones extra que protegen la geolocalización:
regiones sin padre, puntos representativos fuera de su polígono, nombres
normalizados vacíos y conteo de localidades contra la fuente.

No hace: no corrige nada; solo informa.
"""

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import Connection, text

# El Zócalo de la Ciudad de México (Plaza de la Constitución), en grados.
ZOCALO_LON_LAT = (-99.1332, 19.4326)
CDMX_STATE_CODE = "09"
CUAUHTEMOC_CODE = "09015"
# Cuántos nombres de ejemplo se muestran en el reporte.
ENIE_SAMPLE_SIZE = 5


@dataclass(frozen=True, slots=True)
class Expectations:
    """Valores esperados para la validación.

    Attributes:
        state_count: Número de entidades (32 en México).
        cdmx_municipality_count: Alcaldías de la CDMX (16).
        catalog_municipalities: Nombre de cada municipio por clave, según el
            catálogo oficial de la edición (fuente independiente de la capa).
        locality_count: Localidades distintas en las capas de origen (unión
            de claves de 00l y 00lpr: 46,894 vienen en ambas).
        locality_polygon_count: Localidades con polígono (00l).
        min_enie_names: Mínimo de nombres con Ñ a comparar (§12 pide 5).
    """

    state_count: int
    cdmx_municipality_count: int
    catalog_municipalities: Mapping[str, str]
    locality_count: int
    locality_polygon_count: int
    min_enie_names: int


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Resultado de una revisión.

    Attributes:
        name: Qué se revisó, en español.
        passed: Si pasó.
        expected: Valor esperado, legible.
        actual: Valor obtenido, legible.
    """

    name: str
    passed: bool
    expected: str
    actual: str


def _scalar(conn: Connection, sql: str, params: Mapping[str, object] | None = None) -> int:
    return int(conn.execute(text(sql), dict(params or {})).scalar_one() or 0)


def _has_enie(name: str) -> bool:
    return any(c in "ñÑ" for c in unicodedata.normalize("NFC", name))


def check_states(conn: Connection, exp: Expectations) -> CheckResult:
    """§12: 32 entidades."""
    count = _scalar(
        conn, "SELECT count(*) FROM regions WHERE level = 'state' AND country_code = 'MEX'"
    )
    return CheckResult(
        "Entidades federativas", count == exp.state_count, str(exp.state_count), str(count)
    )


def check_municipalities(conn: Connection, exp: Expectations) -> CheckResult:
    """§12: municipios iguales al catálogo de la edición (mismas claves, no solo el total)."""
    codes = set(
        conn.execute(
            text("SELECT code FROM regions WHERE level = 'municipality' AND country_code = 'MEX'")
        ).scalars()
    )
    expected = set(exp.catalog_municipalities)
    missing = sorted(expected - codes)
    extra = sorted(codes - expected)
    detail = f"{len(codes):,}"
    if missing or extra:
        detail += f" (faltan {missing[:5]}, sobran {extra[:5]})"
    return CheckResult(
        "Municipios = catálogo oficial (claves)",
        not missing and not extra,
        f"{len(expected):,}",
        detail,
    )


def check_cdmx(conn: Connection, exp: Expectations) -> CheckResult:
    """§12: la CDMX con 16 alcaldías."""
    count = _scalar(
        conn,
        "SELECT count(*) FROM regions m JOIN regions s ON s.id = m.parent_id "
        "WHERE m.level = 'municipality' AND s.code = :cdmx AND m.display_prefix = 'Alcaldía'",
        {"cdmx": CDMX_STATE_CODE},
    )
    return CheckResult(
        "Alcaldías de la CDMX",
        count == exp.cdmx_municipality_count,
        str(exp.cdmx_municipality_count),
        str(count),
    )


def check_valid_geometries(conn: Connection, exp: Expectations) -> CheckResult:
    """§12: sin geometrías inválidas ni vacías."""
    bad = _scalar(
        conn,
        "SELECT count(*) FROM regions "
        "WHERE geom IS NOT NULL AND (NOT ST_IsValid(geom) OR ST_IsEmpty(geom))",
    )
    return CheckResult("Geometrías inválidas o vacías", bad == 0, "0", f"{bad:,}")


def check_enie_names(conn: Connection, exp: Expectations) -> CheckResult:
    """§12: nombres con Ñ correctos, comparados contra el catálogo oficial.

    Se comparan **todos** los municipios cuyo nombre lleva Ñ en el catálogo
    (CSV en cp1252) contra la base (cargada desde el shapefile en UTF-8): si
    algún encoding estuviera mal, no coincidirían. Se exige un mínimo de
    nombres comparados (§12 pide 5).
    """
    with_enie = {c: n for c, n in exp.catalog_municipalities.items() if _has_enie(n)}
    rows = conn.execute(
        text("SELECT code, name FROM regions WHERE code = ANY(:codes)"),
        {"codes": list(with_enie)},
    ).all()
    stored: dict[str, str] = {str(code): str(name) for code, name in rows}
    mismatches = [c for c, n in with_enie.items() if stored.get(c) != n]
    sample = ", ".join(sorted(with_enie.values())[:ENIE_SAMPLE_SIZE])
    return CheckResult(
        "Nombres con Ñ idénticos al catálogo",
        len(with_enie) >= exp.min_enie_names and not mismatches,
        f"≥ {exp.min_enie_names} y 0 diferencias",
        f"{len(with_enie)} comparados, {len(mismatches)} diferencias (p. ej. {sample})",
    )


def check_zocalo(conn: Connection, exp: Expectations) -> CheckResult:
    """§12: el Zócalo cae en el estado 09 y en la alcaldía Cuauhtémoc."""
    codes = sorted(
        conn.execute(
            text(
                "SELECT code FROM regions WHERE level IN ('state', 'municipality') "
                "AND ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))"
            ),
            {"lon": ZOCALO_LON_LAT[0], "lat": ZOCALO_LON_LAT[1]},
        ).scalars()
    )
    expected = [CDMX_STATE_CODE, CUAUHTEMOC_CODE]
    return CheckResult("El Zócalo cae en 09 y 09015", codes == expected, str(expected), str(codes))


def check_orphans(conn: Connection, exp: Expectations) -> CheckResult:
    """Extra: toda región que no es país tiene padre."""
    count = _scalar(
        conn, "SELECT count(*) FROM regions WHERE level <> 'country' AND parent_id IS NULL"
    )
    return CheckResult("Regiones sin padre", count == 0, "0", f"{count:,}")


def check_points_inside(conn: Connection, exp: Expectations) -> CheckResult:
    """Extra: el punto representativo de cada polígono cae dentro de él."""
    count = _scalar(
        conn,
        "SELECT count(*) FROM regions WHERE geom IS NOT NULL AND NOT ST_Intersects(geom, centroid)",
    )
    return CheckResult("Puntos representativos fuera de su polígono", count == 0, "0", f"{count:,}")


def check_locality_polygons(conn: Connection, exp: Expectations) -> CheckResult:
    """Extra: las localidades que tienen polígono lo conservaron.

    Si una clave viene como polígono y como punto, debe quedar el polígono.
    """
    count = _scalar(
        conn, "SELECT count(*) FROM regions WHERE level = 'locality' AND geom IS NOT NULL"
    )
    return CheckResult(
        "Localidades con polígono",
        count == exp.locality_polygon_count,
        f"{exp.locality_polygon_count:,}",
        f"{count:,}",
    )


def check_localities(conn: Connection, exp: Expectations) -> CheckResult:
    """Extra: todas las localidades distintas de las capas de origen quedaron cargadas."""
    count = _scalar(conn, "SELECT count(*) FROM regions WHERE level = 'locality'")
    return CheckResult(
        "Localidades cargadas",
        count == exp.locality_count,
        f"{exp.locality_count:,}",
        f"{count:,}",
    )


def check_name_norm(conn: Connection, exp: Expectations) -> CheckResult:
    """Extra: ningún nombre normalizado vacío (romperían la búsqueda)."""
    count = _scalar(conn, "SELECT count(*) FROM regions WHERE name_norm = ''")
    return CheckResult("Nombres normalizados vacíos", count == 0, "0", f"{count:,}")


ALL_CHECKS = (
    check_states,
    check_municipalities,
    check_cdmx,
    check_valid_geometries,
    check_enie_names,
    check_zocalo,
    check_orphans,
    check_points_inside,
    check_localities,
    check_locality_polygons,
    check_name_norm,
)


def run_checks(conn: Connection, exp: Expectations) -> list[CheckResult]:
    """Ejecuta todas las revisiones.

    Args:
        conn: Conexión a la base a validar.
        exp: Valores esperados.

    Returns:
        Un resultado por revisión, en orden.
    """
    return [check(conn, exp) for check in ALL_CHECKS]
