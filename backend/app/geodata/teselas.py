"""Generación de PMTiles por capa a partir de la tabla ``regions``.

Para cada capa (países, estados, municipios, localidades):

1. ``ogr2ogr`` exporta de PostGIS a GeoJSONSeq (un objeto por línea, que
   tippecanoe lee en paralelo) solo los atributos que necesita el mapa:
   ``id``, ``code``, ``name``, ``display_prefix`` y ``level``.
2. ``tippecanoe`` genera el ``.pmtiles`` con los zooms de la especificación
   §12, simplificando por nivel de zoom.
3. ``pmtiles verify`` revisa el archivo.
4. Se copia verificado (SHA-256) a ``geodata/output``, de donde lo sirve nginx.

Todo el trabajo pesado ocurre en la carpeta de trabajo del disco de Linux
(ADR-0008); a ``/mnt/d`` solo se copia el resultado final.

No hace: no carga datos ni genera el mapa base (eso es ``mapa_base.sh``).
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.geodata.carga import PostgresTarget, copy_verified

logger = logging.getLogger(__name__)

# tippecanoe sobre municipios a resolución completa tarda minutos; 1 h es un
# tope para no colgar el comando indefinidamente.
TOOL_TIMEOUT_SECONDS = 60 * 60
PMTILES_BIN = Path.home() / ".local" / "bin" / "pmtiles"
# Atribución obligatoria (ADR-0008); queda en los metadatos de cada archivo.
ATTRIBUTION = "© INEGI · Natural Earth"


@dataclass(frozen=True, slots=True)
class TileLayer:
    """Una capa de teselas.

    Attributes:
        name: Nombre de la capa y del archivo (``states`` → ``states.pmtiles``).
        description: Descripción para los metadatos.
        where: Filtro SQL sobre ``regions`` (constante del módulo).
        geometry_sql: Columna geométrica a exportar.
        min_zoom: Primer zoom donde aparece (especificación §12).
        max_zoom: Último zoom generado; MapLibre amplía a partir de ahí.
        is_point: ``True`` para capas de puntos.
    """

    name: str
    description: str
    where: str
    geometry_sql: str
    min_zoom: int
    max_zoom: int
    is_point: bool


# Zooms de la especificación §12: países 0–6, estados 2–10, municipios 5–14,
# localidades (puntos) desde 10. 14 es el máximo de tippecanoe por defecto y
# el nivel de detalle de calle.
LAYERS: tuple[TileLayer, ...] = (
    TileLayer("countries", "Países", "level = 'country'", "geom", 0, 6, False),
    TileLayer("states", "Estados de México (INEGI)", "level = 'state'", "geom", 2, 10, False),
    TileLayer(
        "municipalities",
        "Municipios y alcaldías (INEGI)",
        "level = 'municipality'",
        "geom",
        5,
        14,
        False,
    ),
    # Todas las localidades como puntos: las que tienen polígono usan su punto
    # representativo, para que el mapa no se sature de formas a zoom 10.
    TileLayer("localities", "Localidades (INEGI)", "level = 'locality'", "centroid", 10, 14, True),
)

_ATTRIBUTES = ("id", "code", "name", "display_prefix", "level")


class TileGenerationError(Exception):
    """Una herramienta externa (ogr2ogr, tippecanoe o pmtiles) falló."""


def run_tool(command: list[str], env: dict[str, str] | None = None) -> str:
    """Ejecuta una herramienta externa y devuelve su salida.

    Args:
        command: Comando como lista de argumentos (sin shell).
        env: Variables de entorno (por defecto, las del proceso).

    Returns:
        Salida estándar y de error, concatenadas.

    Raises:
        TileGenerationError: Si la herramienta termina con error.
    """
    result = subprocess.run(  # noqa: S603 — comandos armados sin shell, con rutas locales y constantes
        command,
        env=env,
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise TileGenerationError(
            f"{Path(command[0]).name} falló: {(result.stderr or result.stdout).strip()[-2000:]}"
        )
    return result.stdout + result.stderr


def build_export_command(layer: TileLayer, target: PostgresTarget, output: Path) -> list[str]:
    """Arma el comando que exporta una capa de ``regions`` a GeoJSONSeq.

    Args:
        layer: Capa a exportar.
        target: Base de datos de origen.
        output: Archivo ``.geojsonl`` de salida.

    Returns:
        El comando como lista de argumentos.
    """
    columns = ", ".join(
        f"{column}::text AS {column}" if column == "level" else column for column in _ATTRIBUTES
    )
    sql = (
        f"SELECT {columns}, {layer.geometry_sql} AS geom FROM regions "  # noqa: S608 — solo constantes del módulo
        f"WHERE {layer.where} ORDER BY id"
    )
    return [
        "ogr2ogr",
        "-f",
        "GeoJSONSeq",
        str(output),
        target.ogr_dsn,
        "-sql",
        sql,
        # 6 decimales ≈ 11 cm: más precisión no se nota en el mapa y pesa más.
        "-lco",
        "COORDINATE_PRECISION=6",
        "-overwrite",
    ]


def build_tippecanoe_command(layer: TileLayer, source: Path, output: Path) -> list[str]:
    """Arma el comando de tippecanoe para una capa.

    Args:
        layer: Capa a generar.
        source: GeoJSONSeq exportado.
        output: Archivo ``.pmtiles`` de salida.

    Returns:
        El comando como lista de argumentos.
    """
    command = [
        "tippecanoe",
        "-o",
        str(output),
        "--force",
        "-l",
        layer.name,
        "-n",
        layer.description,
        "-A",
        ATTRIBUTION,
        "-Z",
        str(layer.min_zoom),
        "-z",
        str(layer.max_zoom),
        # El id numérico de la región se vuelve el id de la figura: MapLibre
        # lo necesita para resaltar la región bajo el cursor (feature-state).
        "--use-attribute-for-id=id",
        # Lectura en paralelo del GeoJSONSeq.
        "-P",
    ]
    for attribute in _ATTRIBUTES:
        command += ["-y", attribute]
    if layer.is_point:
        # A zoom 10 hay ~344 mil puntos: se descartan los más densos solo
        # donde no caben en una tesela; a zoom 14 aparecen todos.
        command.append("--drop-densest-as-needed")
    else:
        # Municipios vecinos comparten borde: se simplifican igual de los dos
        # lados para que no aparezcan huecos ni encimados entre ellos.
        command.append("--detect-shared-borders")
        command.append("--coalesce-densest-as-needed")
    command.append(str(source))
    return command


@dataclass(frozen=True, slots=True)
class TileResult:
    """Resultado de generar una capa.

    Attributes:
        layer: Nombre de la capa.
        features: Figuras exportadas.
        size_bytes: Tamaño del ``.pmtiles``.
        path: Ruta final en ``geodata/output``.
        verify_output: Salida de ``pmtiles verify``.
    """

    layer: str
    features: int
    size_bytes: int
    path: Path
    verify_output: str


def generate_layer(
    layer: TileLayer, target: PostgresTarget, work_dir: Path, output_dir: Path
) -> TileResult:
    """Genera, verifica y publica el PMTiles de una capa.

    Args:
        layer: Capa a generar.
        target: Base de datos de origen.
        work_dir: Carpeta de trabajo en el disco de Linux.
        output_dir: Carpeta servida por nginx (``geodata/output``).

    Returns:
        El resultado con tamaño y verificación.

    Raises:
        TileGenerationError: Si alguna herramienta falla.
    """
    tiles_dir = work_dir / "teselas"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    geojson = tiles_dir / f"{layer.name}.geojsonl"
    pmtiles = tiles_dir / f"{layer.name}.pmtiles"
    run_tool(
        build_export_command(layer, target, geojson),
        env={**os.environ, "PGPASSWORD": target.password},
    )
    with geojson.open("rb") as handle:
        features = sum(1 for _ in handle)
    logger.info(f"{layer.name}: {features:,} figuras exportadas; generando teselas")
    run_tool(build_tippecanoe_command(layer, geojson, pmtiles))
    verify_output = run_tool([str(PMTILES_BIN), "verify", str(pmtiles)])
    final = output_dir / pmtiles.name
    copy_verified(pmtiles, final)
    geojson.unlink()
    return TileResult(layer.name, features, final.stat().st_size, final, verify_output.strip())


def show_header(path: Path) -> str:
    """Devuelve la cabecera de un PMTiles (zooms, límites, tipo de tesela).

    Args:
        path: Archivo ``.pmtiles``.

    Returns:
        La salida de ``pmtiles show``.
    """
    return run_tool([str(PMTILES_BIN), "show", str(path)]).strip()
