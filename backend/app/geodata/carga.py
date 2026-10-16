"""Carga de geodatos de INEGI y Natural Earth a la tabla ``regions``.

Cómo funciona (especificación §12, ADR-0008):

0. Toda entrada que no esté ya en la carpeta de trabajo (disco de Linux) se
   copia ahí y se verifica con SHA-256: GDAL recibió bytes dañados al leer
   directamente de ``/mnt/d`` en WSL (ADR-0008).
1. ``ogr2ogr`` (GDAL) lee cada shapefile con el encoding que decidió la
   inspección, lo reproyecta a EPSG:4326 y lo deja en el esquema de trabajo
   ``staging_geo`` usando ``COPY``, en lotes con commit por lote.
2. Python calcula ``name_norm`` con ``app.domain.names.normalize_name`` (la
   misma función que usa el buscador) y lo pasa a la base con ``COPY``.
3. Un ``INSERT ... SELECT`` por lote de claves repara geometrías inválidas
   (``ST_MakeValid``), se queda solo con polígonos, calcula el punto
   representativo (``ST_PointOnSurface``) y el ``bbox``, enlaza al padre
   por prefijo de clave INEGI y hace ``upsert`` por ``code``: correrlo dos
   veces no duplica nada.

Orden: países → México (unión de los estados INEGI) → estados → municipios
→ localidades (primero las puntuales y luego las de polígono, para que si
una clave apareciera en ambas gane la que tiene polígono). Al final se
aplican los alias, los términos de búsqueda y los códigos de país
(``terminos``, ADR-0009).

No hace: no descarga ni valida los criterios de aceptación (eso es
``descargar`` y ``validar``). No borra regiones que desaparezcan en una
edición nueva de INEGI: eso se decidirá cuando haya noticias que las usen.
"""

import csv
import logging
import os
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, text

from app.domain.names import normalize_name
from app.geodata.descarga import sha256_file
from app.geodata.terminos import (
    apply_country_codes,
    apply_search_terms,
    read_country_codes,
    read_search_terms,
)

logger = logging.getLogger(__name__)

STAGING_SCHEMA = "staging_geo"
# CLAUDE.md §6.3: cargas masivas en lotes de 10,000 a 50,000 con commit por lote.
BATCH_SIZE = 20_000
# ogr2ogr con 292 mil localidades tarda menos de un minuto; 30 min es un tope
# holgado para no colgar el comando si GDAL se atora.
OGR2OGR_TIMEOUT_SECONDS = 30 * 60

MEXICO_CODE = "MEX"
MEXICO_NAME = "México"
CDMX_STATE_CODE = "09"
# Natural Earth pone -99 en ISO_A3 cuando no aplica (Francia, Noruega...).
NE_MISSING_ISO = "-99"
# Longitudes de las claves INEGI (CVEGEO): estado 2, municipio 5.
STATE_CODE_LENGTH = 2
MUNICIPALITY_CODE_LENGTH = 5

# Nombres de encoding de Python → nombres que entiende GDAL (SHAPE_ENCODING).
GDAL_ENCODINGS: dict[str, str] = {
    "utf-8": "UTF-8",
    "cp1252": "CP1252",
    "latin1": "ISO-8859-1",
    "cp850": "CP850",
}

# Solo nombres de tabla simples: se interpolan en SQL y no deben venir de afuera.
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")

# Geometría de polígono lista para guardar: se repara solo si es inválida
# (ST_MakeValid es caro) y se descartan líneas o puntos que la reparación
# pudiera producir, quedando siempre un MultiPolygon.
_VALID_POLYGON = (
    "ST_Multi(ST_CollectionExtract("
    "CASE WHEN ST_IsValid(s.geom) THEN s.geom ELSE ST_MakeValid(s.geom) END, 3))"
)
_BBOX = "ARRAY[ST_XMin(g.geom), ST_YMin(g.geom), ST_XMax(g.geom), ST_YMax(g.geom)]"
_UPSERT = """
    ON CONFLICT (code) DO UPDATE SET
        level = EXCLUDED.level,
        parent_id = EXCLUDED.parent_id,
        country_code = EXCLUDED.country_code,
        name = EXCLUDED.name,
        name_norm = EXCLUDED.name_norm,
        display_prefix = EXCLUDED.display_prefix,
        geom = EXCLUDED.geom,
        centroid = EXCLUDED.centroid,
        bbox = EXCLUDED.bbox,
        source = EXCLUDED.source
"""
_INSERT_COLUMNS = (
    "INSERT INTO regions (level, code, parent_id, country_code, name, name_norm, "
    "display_prefix, geom, centroid, bbox, source)"
)


class GeodataLoadError(Exception):
    """La carga no se pudo completar (GDAL falló, faltan padres, alias inválidos...)."""


@dataclass(frozen=True, slots=True)
class LayerInput:
    """Una capa de entrada para el cargador.

    Attributes:
        table: Tabla destino dentro de ``staging_geo``.
        path: Archivo de origen (shapefile o GeoJSON).
        encoding: Encoding de los textos (nombre de Python, ``utf-8``...).
        is_point: ``True`` si la capa es de puntos.
        fields: Campos a copiar (se guardan en minúsculas).
    """

    table: str
    path: Path
    encoding: str
    is_point: bool
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LoadInputs:
    """Todo lo que necesita una corrida de carga.

    Attributes:
        countries: Países de Natural Earth.
        states: Estados de INEGI (00ent).
        municipalities: Municipios de INEGI (00mun).
        locality_points: Localidades rurales puntuales (00lpr).
        locality_polygons: Localidades con polígono (00l).
        aliases_csv: Lista curada de alias (``geodata/aliases.csv``).
        search_terms_csv: Lista curada de términos de búsqueda
            (``geodata/search_terms.csv``, ADR-0009).
        inegi_source: Texto para la columna ``source`` de las filas de INEGI.
        natural_earth_source: Texto para ``source`` de los países.
    """

    countries: LayerInput
    states: LayerInput
    municipalities: LayerInput
    locality_points: LayerInput
    locality_polygons: LayerInput
    aliases_csv: Path
    search_terms_csv: Path
    inegi_source: str
    natural_earth_source: str


@dataclass(frozen=True, slots=True)
class PostgresTarget:
    """Datos de conexión para ``ogr2ogr``.

    Attributes:
        host: Servidor.
        port: Puerto.
        dbname: Base de datos.
        user: Usuario.
        password: Contraseña (se pasa por variable de entorno, no en la
            línea de comandos, para que no aparezca en la lista de procesos).
    """

    host: str
    port: int
    dbname: str
    user: str
    password: str

    @property
    def ogr_dsn(self) -> str:
        """Cadena de conexión de GDAL, sin contraseña."""
        return f"PG:host={self.host} port={self.port} dbname={self.dbname} user={self.user}"


@dataclass(frozen=True, slots=True)
class LoadSummary:
    """Resultado de la carga.

    Attributes:
        counts: Regiones por nivel después de la carga.
        repaired: Geometrías inválidas que se repararon, por capa.
        aliases: Alias aplicados.
        search_terms: Regiones con términos de búsqueda curados.
        country_codes: Países con sus códigos para los proveedores.
    """

    counts: dict[str, int]
    repaired: dict[str, int]
    aliases: int
    search_terms: int
    country_codes: int


def copy_verified(source: Path, destination: Path) -> None:
    """Copia un archivo y comprueba que la copia sea idéntica (SHA-256).

    Args:
        source: Archivo original.
        destination: Ruta de la copia.

    Raises:
        GeodataLoadError: Si la copia no coincide byte por byte.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha256_file(source) != sha256_file(destination):
        raise GeodataLoadError(f"La copia de {source.name} no coincide con el original.")


def stage_inputs(inputs: LoadInputs, work_dir: Path) -> LoadInputs:
    """Asegura que GDAL lea las capas desde la carpeta de trabajo en Linux.

    Las capas que ya están dentro de ``work_dir`` (por ejemplo, las que
    extrajo la inspección verificando el CRC del ZIP) se usan tal cual. Las
    demás se copian, con todos sus archivos hermanos (``.shp``, ``.dbf``,
    ``.prj``...), y se verifican.

    Args:
        inputs: Entradas originales.
        work_dir: Carpeta de trabajo (``GEODATA_WORK_DIR``).

    Returns:
        Las mismas entradas, apuntando a rutas dentro de ``work_dir``.
    """
    staged_dir = work_dir / "entrada"

    def stage(layer: LayerInput) -> LayerInput:
        if layer.path.resolve().is_relative_to(work_dir.resolve()):
            return layer
        for sibling in layer.path.parent.glob(f"{layer.path.stem}.*"):
            copy_verified(sibling, staged_dir / sibling.name)
        return replace(layer, path=staged_dir / layer.path.name)

    return replace(
        inputs,
        countries=stage(inputs.countries),
        states=stage(inputs.states),
        municipalities=stage(inputs.municipalities),
        locality_points=stage(inputs.locality_points),
        locality_polygons=stage(inputs.locality_polygons),
    )


def _staging(table: str) -> str:
    """Nombre calificado de una tabla de trabajo, validando que sea seguro."""
    if not _SAFE_IDENTIFIER.match(table):
        raise GeodataLoadError(f"Nombre de tabla no permitido: {table!r}")
    return f"{STAGING_SCHEMA}.{table}"


def build_ogr2ogr_command(layer: LayerInput, target: PostgresTarget) -> list[str]:
    """Arma el comando de ``ogr2ogr`` que copia una capa a ``staging_geo``.

    Args:
        layer: Capa de entrada.
        target: Base de datos destino.

    Returns:
        El comando como lista de argumentos (sin pasar por una shell).

    Raises:
        GeodataLoadError: Si el encoding no tiene equivalente en GDAL.

    Example:
        >>> build_ogr2ogr_command(states, target)[:4]
        ['ogr2ogr', '-f', 'PostgreSQL', 'PG:host=localhost ...']
    """
    if layer.encoding not in GDAL_ENCODINGS:
        raise GeodataLoadError(f"Encoding sin equivalente en GDAL: {layer.encoding}")
    return [
        "ogr2ogr",
        "-f",
        "PostgreSQL",
        target.ogr_dsn,
        str(layer.path),
        "-nln",
        _staging(layer.table),
        "-overwrite",
        "-t_srs",
        "EPSG:4326",
        "-nlt",
        "POINT" if layer.is_point else "PROMOTE_TO_MULTI",
        "-select",
        ",".join(layer.fields),
        "-lco",
        "GEOMETRY_NAME=geom",
        "-lco",
        "FID=fid",
        "-lco",
        "SPATIAL_INDEX=NONE",
        "-lco",
        "LAUNDER=YES",
        # Commit cada BATCH_SIZE registros (CLAUDE.md §6.3).
        "-gt",
        str(BATCH_SIZE),
        "--config",
        "PG_USE_COPY",
        "YES",
        "--config",
        "SHAPE_ENCODING",
        GDAL_ENCODINGS[layer.encoding],
    ]


def copy_to_staging(layer: LayerInput, target: PostgresTarget) -> None:
    """Ejecuta ``ogr2ogr`` para una capa.

    Args:
        layer: Capa de entrada.
        target: Base de datos destino.

    Raises:
        GeodataLoadError: Si GDAL termina con error (incluye su mensaje).
    """
    command = build_ogr2ogr_command(layer, target)
    result = subprocess.run(  # noqa: S603 — comando armado sin shell, con rutas locales y constantes
        command,
        env={**os.environ, "PGPASSWORD": target.password},
        capture_output=True,
        text=True,
        timeout=OGR2OGR_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise GeodataLoadError(
            f"ogr2ogr falló con {layer.path.name}: {result.stderr.strip()[-2000:]}"
        )


def fill_name_norm(conn: Connection, table: str, name_sql: str) -> int:
    """Agrega ``name_norm`` a una tabla de trabajo, calculado en Python.

    Args:
        conn: Conexión dentro de una transacción.
        table: Tabla de ``staging_geo``.
        name_sql: Expresión SQL del nombre (por ejemplo ``s.nomgeo``).

    Returns:
        Número de filas procesadas.
    """
    staging = _staging(table)
    conn.execute(text(f"ALTER TABLE {staging} ADD COLUMN IF NOT EXISTS name_norm text"))
    rows = conn.execute(text(f"SELECT s.fid, {name_sql} FROM {staging} s")).all()  # noqa: S608 — tabla validada y expresión constante del cargador
    driver = conn.connection.driver_connection
    if driver is None:  # pragma: no cover — siempre hay conexión dentro de una transacción
        raise GeodataLoadError("No hay conexión de psycopg disponible.")
    with driver.cursor() as cursor:
        cursor.execute(
            "CREATE TEMP TABLE tmp_name_norm (fid bigint PRIMARY KEY, name_norm text) "
            "ON COMMIT DROP"
        )
        with cursor.copy("COPY tmp_name_norm (fid, name_norm) FROM STDIN") as copy:
            for fid, name in rows:
                copy.write_row((fid, normalize_name(name or "")))
    conn.execute(
        text(
            f"UPDATE {staging} s SET name_norm = t.name_norm "  # noqa: S608 — tabla validada
            "FROM tmp_name_norm t WHERE s.fid = t.fid"
        )
    )
    return len(rows)


def _count(conn: Connection, sql: str, params: dict[str, Any] | None = None) -> int:
    value = conn.execute(text(sql), params or {}).scalar_one()
    return int(value or 0)


def _max_fid(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return _count(conn, f"SELECT max(fid) FROM {_staging(table)}")  # noqa: S608 — tabla validada


def _count_invalid(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return _count(conn, f"SELECT count(*) FROM {_staging(table)} WHERE NOT ST_IsValid(geom)")  # noqa: S608 — tabla validada


def _insert_in_batches(engine: Engine, table: str, select_sql: str, source: str) -> None:
    """Inserta por lotes de ``fid`` con commit por lote (CLAUDE.md §6.3)."""
    last = _max_fid(engine, table)
    for low in range(0, last, BATCH_SIZE):
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"{_INSERT_COLUMNS} {select_sql} AND s.fid > :low AND s.fid <= :high {_UPSERT}"
                ),
                {"low": low, "high": low + BATCH_SIZE, "source": source},
            )


def _check_parents(engine: Engine, table: str, prefix_length: int) -> None:
    """Falla si alguna fila no tiene a su región padre ya cargada."""
    with engine.connect() as conn:
        orphans = conn.execute(
            text(
                f"SELECT s.cvegeo FROM {_staging(table)} s "  # noqa: S608 — tabla validada
                "LEFT JOIN regions p ON p.code = left(s.cvegeo, :n) "
                "WHERE p.id IS NULL LIMIT 10"
            ),
            {"n": prefix_length},
        ).scalars()
        missing = list(orphans)
    if missing:
        raise GeodataLoadError(f"Claves sin región padre en {table}: {', '.join(missing)}")


def load_countries(engine: Engine, layer: LayerInput, source: str) -> None:
    """Carga los países de Natural Earth, excepto México.

    El código es ``ISO_A3`` cuando es válido y único; si no, ``ADM0_A3``
    (ADR-0008). México se arma aparte desde los estados de INEGI.
    """
    with engine.begin() as conn:
        fill_name_norm(conn, layer.table, "COALESCE(NULLIF(s.name_es, ''), s.name)")
    staging = _staging(layer.table)
    select_sql = f"""
        SELECT 'country'::region_level, c.code, NULL::bigint, c.code,
               COALESCE(NULLIF(s.name_es, ''), s.name), s.name_norm, 'País',
               g.geom, ST_PointOnSurface(g.geom), {_BBOX}, :source
        FROM {staging} s
        CROSS JOIN LATERAL (SELECT {_VALID_POLYGON} AS geom) g
        CROSS JOIN LATERAL (
            SELECT CASE
                WHEN s.iso_a3 <> '{NE_MISSING_ISO}'
                     AND (SELECT count(*) FROM {staging} d WHERE d.iso_a3 = s.iso_a3) = 1
                THEN s.iso_a3 ELSE s.adm0_a3 END AS code
        ) c
        WHERE s.adm0_a3 <> '{MEXICO_CODE}'
    """  # noqa: S608 — solo constantes del cargador y tablas validadas
    _insert_in_batches(engine, layer.table, select_sql, source)


def load_mexico(engine: Engine, states: LayerInput, source: str) -> None:
    """Crea la región país México como unión de los estados de INEGI (ADR-0008)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                {_INSERT_COLUMNS}
                SELECT 'country'::region_level, :code, NULL::bigint, :code, :name, :name_norm,
                       'País', g.geom, ST_PointOnSurface(g.geom), {_BBOX}, :source
                FROM (
                    SELECT ST_Multi(ST_CollectionExtract(
                               ST_MakeValid(ST_Union({_VALID_POLYGON})), 3)) AS geom
                    FROM {_staging(states.table)} s
                ) g
                {_UPSERT}
                """  # noqa: S608 — solo constantes del cargador y tablas validadas
            ),
            {
                "code": MEXICO_CODE,
                "name": MEXICO_NAME,
                "name_norm": normalize_name(MEXICO_NAME),
                "source": source,
            },
        )


def load_inegi_polygons(
    engine: Engine, layer: LayerInput, level: str, source: str, parent_code_sql: str
) -> None:
    """Carga una capa de polígonos de INEGI (estados, municipios o localidades).

    Args:
        engine: Conexión a la base.
        layer: Capa de entrada.
        level: Nivel de ``regions`` (``state``, ``municipality``, ``locality``).
        source: Texto para la columna ``source``.
        parent_code_sql: Expresión SQL con la clave del padre (por ejemplo
            ``left(s.cvegeo, 2)``).
    """
    with engine.begin() as conn:
        fill_name_norm(conn, layer.table, "s.nomgeo")
    prefix = {
        "state": f"CASE WHEN s.cvegeo = '{CDMX_STATE_CODE}' THEN 'Entidad federativa' "
        "ELSE 'Estado' END",
        "municipality": f"CASE WHEN s.cvegeo LIKE '{CDMX_STATE_CODE}%' THEN 'Alcaldía' "
        "ELSE 'Municipio' END",
        "locality": "'Localidad'",
    }[level]
    select_sql = f"""
        SELECT CAST(:level AS region_level), s.cvegeo, p.id, '{MEXICO_CODE}', s.nomgeo,
               s.name_norm, {prefix}, g.geom, ST_PointOnSurface(g.geom), {_BBOX}, :source
        FROM {_staging(layer.table)} s
        CROSS JOIN LATERAL (SELECT {_VALID_POLYGON} AS geom) g
        JOIN regions p ON p.code = {parent_code_sql}
        WHERE TRUE
    """  # noqa: S608 — solo constantes del cargador y tablas validadas
    last = _max_fid(engine, layer.table)
    for low in range(0, last, BATCH_SIZE):
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"{_INSERT_COLUMNS} {select_sql} AND s.fid > :low AND s.fid <= :high {_UPSERT}"
                ),
                {"low": low, "high": low + BATCH_SIZE, "source": source, "level": level},
            )


def load_locality_points(engine: Engine, layer: LayerInput, source: str) -> None:
    """Carga las localidades rurales puntuales: sin polígono, solo su punto."""
    with engine.begin() as conn:
        fill_name_norm(conn, layer.table, "s.nomgeo")
    select_sql = f"""
        SELECT 'locality'::region_level, s.cvegeo, p.id, '{MEXICO_CODE}', s.nomgeo, s.name_norm,
               'Localidad', NULL::geometry, s.geom,
               ARRAY[ST_X(s.geom), ST_Y(s.geom), ST_X(s.geom), ST_Y(s.geom)], :source
        FROM {_staging(layer.table)} s
        JOIN regions p ON p.code = left(s.cvegeo, {MUNICIPALITY_CODE_LENGTH})
        WHERE TRUE
    """  # noqa: S608 — solo constantes del cargador y tablas validadas
    _insert_in_batches(engine, layer.table, select_sql, source)


def read_aliases(path: Path) -> dict[str, list[str]]:
    """Lee la lista curada de alias.

    Args:
        path: CSV con columnas ``code``, ``alias`` y ``nota``.

    Returns:
        Alias por clave de región, sin repetir y en el orden del archivo.
    """
    aliases: dict[str, list[str]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            alias = row["alias"].strip()
            if alias and alias not in aliases[row["code"].strip()]:
                aliases[row["code"].strip()].append(alias)
    return dict(aliases)


def apply_aliases(engine: Engine, aliases: dict[str, list[str]]) -> int:
    """Reemplaza los alias de las regiones con los de la lista curada.

    Args:
        engine: Conexión a la base.
        aliases: Alias por clave de región.

    Returns:
        Número total de alias aplicados.

    Raises:
        GeodataLoadError: Si algún alias apunta a una clave que no existe.
    """
    with engine.begin() as conn:
        existing = set(
            conn.execute(
                text("SELECT code FROM regions WHERE code = ANY(:codes)"),
                {"codes": list(aliases)},
            ).scalars()
        )
        unknown = sorted(set(aliases) - existing)
        if unknown:
            raise GeodataLoadError(f"Alias con claves inexistentes: {', '.join(unknown)}")
        conn.execute(
            text(
                "UPDATE regions SET aliases = '{}', aliases_norm = '{}' "
                "WHERE cardinality(aliases) > 0"
            )
        )
        for code, names in aliases.items():
            conn.execute(
                text("UPDATE regions SET aliases = :a, aliases_norm = :n WHERE code = :code"),
                {"a": names, "n": [normalize_name(name) for name in names], "code": code},
            )
    return sum(len(names) for names in aliases.values())


def run_load(
    engine: Engine, target: PostgresTarget, inputs: LoadInputs, work_dir: Path
) -> LoadSummary:
    """Ejecuta la carga completa.

    Args:
        engine: Conexión síncrona a la base destino.
        target: Datos de conexión para ``ogr2ogr``.
        inputs: Capas de entrada, alias y textos de fuente.
        work_dir: Carpeta de trabajo en el disco de Linux.

    Returns:
        Conteos por nivel, geometrías reparadas y alias aplicados.

    Raises:
        GeodataLoadError: Si algún paso falla.
    """
    inputs = stage_inputs(inputs, work_dir)
    layers = (
        inputs.countries,
        inputs.states,
        inputs.municipalities,
        inputs.locality_points,
        inputs.locality_polygons,
    )
    for layer in layers:
        copy_to_staging(layer, target)
        logger.info(f"{layer.path.name} copiado a {_staging(layer.table)}")
    repaired = {
        layer.table: _count_invalid(engine, layer.table) for layer in layers if not layer.is_point
    }

    load_countries(engine, inputs.countries, inputs.natural_earth_source)
    load_mexico(engine, inputs.states, inputs.inegi_source)
    load_inegi_polygons(engine, inputs.states, "state", inputs.inegi_source, f"'{MEXICO_CODE}'")
    _check_parents(engine, inputs.municipalities.table, STATE_CODE_LENGTH)
    load_inegi_polygons(
        engine,
        inputs.municipalities,
        "municipality",
        inputs.inegi_source,
        f"left(s.cvegeo, {STATE_CODE_LENGTH})",
    )
    for layer in (inputs.locality_points, inputs.locality_polygons):
        _check_parents(engine, layer.table, MUNICIPALITY_CODE_LENGTH)
    load_locality_points(engine, inputs.locality_points, inputs.inegi_source)
    load_inegi_polygons(
        engine,
        inputs.locality_polygons,
        "locality",
        inputs.inegi_source,
        f"left(s.cvegeo, {MUNICIPALITY_CODE_LENGTH})",
    )
    alias_count = apply_aliases(engine, read_aliases(inputs.aliases_csv))
    terms_count = apply_search_terms(engine, read_search_terms(inputs.search_terms_csv))
    codes_count = apply_country_codes(
        engine, read_country_codes(inputs.countries.path, inputs.countries.encoding)
    )

    with engine.begin() as conn:
        for layer in layers:
            conn.execute(text(f"DROP TABLE IF EXISTS {_staging(layer.table)}"))
        counts = {
            str(level): int(total)
            for level, total in conn.execute(
                text("SELECT level, count(*) FROM regions GROUP BY level ORDER BY level")
            )
        }
    # ANALYZE fuera de la transacción para que el planificador use los índices
    # con estadísticas frescas desde la primera consulta.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("ANALYZE regions"))
    return LoadSummary(
        counts=counts,
        repaired=repaired,
        aliases=alias_count,
        search_terms=terms_count,
        country_codes=codes_count,
    )
