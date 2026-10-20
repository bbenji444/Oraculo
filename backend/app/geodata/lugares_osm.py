"""Comando ``make geo-places``: colonias y barrios de OpenStreetMap (ADR-0020).

INEGI no publica colonias, y las notas las nombran todo el tiempo ("Polanco",
"Roma Norte", "Santa Cruz Meyehualco"). El mapa base de México que ya está
descargado (``geodata/output/basemap_mexico.pmtiles``, Protomaps a partir de
OpenStreetMap) trae la capa ``places`` con colonias (``neighbourhood``), zonas
grandes (``macrohood``, como "Nuevo Polanco") y parajes (``locality``), cada uno
con su punto. Este comando los pasa a la tabla ``places``:

1. Copia el PMTiles a la carpeta de trabajo en Linux (GDAL leyó bytes dañados
   desde ``/mnt/d``, ADR-0008) y verifica su SHA-256.
2. ``ogr2ogr`` (driver PMTiles de GDAL ≥ 3.8) lee la capa a zoom 13, donde ya
   aparecen todas las colonias, y la deja en ``staging_geo.osm_places``.
3. Cada lugar se une al municipio de INEGI que lo contiene (``ST_Intersects``):
   lo que cae fuera de México (el recuadro incluye parte de Guatemala y
   Estados Unidos) se descarta.
4. ``name_core`` es el nombre normalizado sin la palabra genérica ("COLONIA
   ROMA NORTE" → "ROMA NORTE"), con la misma lista que usa el geolocalizador.

Se puede repetir: vacía ``places`` y la vuelve a llenar. Con ``--muestra``
solo enseña 5 ejemplos reales sin escribir nada (CLAUDE.md §2.6).

No hace: no descarga nada (el mapa base lo baja ``make geo-basemap``) ni usa
calles ni lugares de interés (``roads``, ``pois``): solo nombres de zonas.
"""

import argparse
import logging
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings
from app.domain.geocoding import GENERIC_PREFIXES
from app.geodata.carga import (
    OGR2OGR_TIMEOUT_SECONDS,
    STAGING_SCHEMA,
    GeodataLoadError,
    PostgresTarget,
    copy_verified,
    fill_name_norm,
)
from app.geodata.consola import configure_cli_logging, heading
from app.geodata.descarga import sha256_file
from app.geodata.mapa_base import OUTPUT_DIR

logger = logging.getLogger(__name__)

BASEMAP_FILE = "basemap_mexico.pmtiles"
PLACES_LAYER = "places"
STAGING_TABLE = "osm_places"
# Zoom 13: ahí ya están todas las colonias (min_zoom 11 a 13); a 14 hay los
# mismos lugares en 4 veces más teselas. Medido el 21/10/2026: 139 mil lugares
# en 3 minutos.
READ_ZOOM = 13
KINDS = ("neighbourhood", "macrohood", "locality")
SOURCE = "OpenStreetMap (Protomaps basemap 4.15.2)"
# Los mismos prefijos del geolocalizador, como expresión regular de PostgreSQL.
_PREFIX_PATTERN = "^(" + "|".join(re.escape(p.strip()) for p in GENERIC_PREFIXES) + ") "
# Lugares de ejemplo para --muestra (búsqueda real del 20/10/2026).
SAMPLE_NAMES = ("POLANCO", "ROMA NORTE", "CONDESA", "NUEVA SANTA MARIA", "SANTA CRUZ MEYEHUALCO")


@dataclass(frozen=True, slots=True)
class PlacesSummary:
    """Resultado de la carga.

    Attributes:
        read: Lugares leídos del mapa base.
        loaded: Lugares guardados (dentro de algún municipio de México).
        by_kind: Guardados por tipo.
    """

    read: int
    loaded: int
    by_kind: dict[str, int]


def build_command(pmtiles: Path, target: PostgresTarget) -> list[str]:
    """Arma el comando de ``ogr2ogr`` que copia la capa de lugares a ``staging_geo``.

    Args:
        pmtiles: Mapa base de México en la carpeta de trabajo.
        target: Base de datos destino.

    Returns:
        El comando como lista de argumentos (sin shell).
    """
    return [
        "ogr2ogr",
        "-f",
        "PostgreSQL",
        target.ogr_dsn,
        str(pmtiles),
        PLACES_LAYER,
        "-oo",
        f"ZOOM_LEVEL={READ_ZOOM}",
        "-nln",
        f"{STAGING_SCHEMA}.{STAGING_TABLE}",
        "-overwrite",
        "-t_srs",
        "EPSG:4326",
        "-nlt",
        "POINT",
        "-select",
        "mvt_id,kind,kind_detail,name,wikidata",
        "-lco",
        "GEOMETRY_NAME=geom",
        "-lco",
        "FID=fid",
        "-lco",
        "LAUNDER=YES",
        "--config",
        "PG_USE_COPY",
        "YES",
    ]


def stage_basemap(output_dir: Path, work_dir: Path) -> Path:
    """Deja el mapa base en la carpeta de trabajo, verificado, y devuelve su ruta.

    Args:
        output_dir: Donde lo dejó ``make geo-basemap``.
        work_dir: Carpeta de trabajo en Linux (``GEODATA_WORK_DIR``).

    Returns:
        Ruta del PMTiles dentro de ``work_dir``.

    Raises:
        GeodataLoadError: Si falta el mapa base.
    """
    source = output_dir / BASEMAP_FILE
    if not source.exists():
        raise GeodataLoadError(f"Falta {source}. Corre primero: wsl make geo-basemap")
    staged = work_dir / "entrada" / BASEMAP_FILE
    same = staged.exists() and staged.stat().st_size == source.stat().st_size
    if not same or sha256_file(staged) != sha256_file(source):
        copy_verified(source, staged)
    return staged


def copy_places(pmtiles: Path, target: PostgresTarget) -> None:
    """Ejecuta ``ogr2ogr``.

    Raises:
        GeodataLoadError: Si GDAL termina con error.
    """
    result = subprocess.run(  # noqa: S603 — comando armado sin shell, con rutas locales y constantes
        build_command(pmtiles, target),
        env={**os.environ, "PGPASSWORD": target.password},
        capture_output=True,
        text=True,
        timeout=OGR2OGR_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise GeodataLoadError(f"ogr2ogr falló con {pmtiles.name}: {result.stderr.strip()[-2000:]}")


_INSERT = f"""
    INSERT INTO places (name, name_core, kind, kind_detail, municipality_id, point, wikidata,
        source)
    SELECT DISTINCT ON (s.mvt_id, s.name)
        s.name, regexp_replace(s.name_norm, :pattern, ''), s.kind, s.kind_detail, m.id, s.geom,
        NULLIF(s.wikidata, ''), :source
    FROM {STAGING_SCHEMA}.{STAGING_TABLE} s
    JOIN regions m ON m.level = 'municipality' AND ST_Intersects(m.geom, s.geom)
    WHERE s.kind = ANY(:kinds) AND btrim(coalesce(s.name, '')) <> ''
        AND btrim(regexp_replace(s.name_norm, :pattern, '')) <> ''
    ORDER BY s.mvt_id, s.name
"""  # noqa: S608 — esquema y tabla constantes del cargador


def load_places(engine: Engine, target: PostgresTarget, pmtiles: Path) -> PlacesSummary:
    """Llena ``places`` desde el mapa base (vacía antes lo que hubiera).

    Args:
        engine: Conexión síncrona a la base destino.
        target: Datos de conexión para ``ogr2ogr``.
        pmtiles: Mapa base ya copiado a la carpeta de trabajo.

    Returns:
        Conteos de lo leído y lo guardado.
    """
    copy_places(pmtiles, target)
    staging = f"{STAGING_SCHEMA}.{STAGING_TABLE}"
    with engine.begin() as conn:
        read = fill_name_norm(conn, STAGING_TABLE, "s.name")
        conn.execute(text(f"CREATE INDEX ON {staging} USING gist (geom)"))
        conn.execute(text("TRUNCATE places"))
        conn.execute(
            text(_INSERT), {"pattern": _PREFIX_PATTERN, "source": SOURCE, "kinds": list(KINDS)}
        )
        by_kind = {
            str(kind): int(count)
            for kind, count in conn.execute(
                text("SELECT kind, count(*) FROM places GROUP BY kind ORDER BY kind")
            )
        }
        conn.execute(text(f"DROP TABLE IF EXISTS {staging}"))
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("ANALYZE places"))
    return PlacesSummary(read=read, loaded=sum(by_kind.values()), by_kind=by_kind)


def show_samples(engine: Engine, names: Sequence[str] = SAMPLE_NAMES) -> None:
    """Enseña cómo quedaron algunos lugares reales, con su municipio y estado.

    Args:
        engine: Conexión a la base.
        names: Núcleos de nombre a buscar (exactos o como inicio).
    """
    with engine.connect() as conn:
        for name in names:
            rows = conn.execute(
                text(
                    """
                    SELECT p.name, p.kind, m.display_prefix || ' ' || m.name AS municipio,
                        e.name AS estado, round(ST_Y(p.point)::numeric, 4) AS lat,
                        round(ST_X(p.point)::numeric, 4) AS lon
                    FROM places p JOIN regions m ON m.id = p.municipality_id
                    JOIN regions e ON e.level = 'state' AND e.code = left(m.code, 2)
                    WHERE p.name_core = :n OR p.name_core LIKE :prefix
                    ORDER BY (p.name_core = :n) DESC, p.name LIMIT 4
                    """
                ),
                {"n": name, "prefix": f"{name} %"},
            ).all()
            logger.info(f"{name}:")
            for row in rows:
                logger.info(
                    f"  · {row.name} ({row.kind}) → {row.municipio}, {row.estado} "
                    f"[{row.lat}, {row.lon}]"
                )
            if not rows:
                logger.info("  (sin coincidencias)")


def main(argv: Sequence[str] | None = None) -> None:
    """Punto de entrada de ``make geo-places``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--muestra", action="store_true", help="Solo enseña ejemplos.")
    args = parser.parse_args(argv)
    configure_cli_logging()
    settings = get_settings()
    engine = create_engine(settings.database_url())
    if args.muestra:
        heading(logger, "Lugares de OpenStreetMap ya cargados (ejemplos reales)")
        show_samples(engine)
        return
    heading(logger, "Copiando el mapa base a la carpeta de trabajo")
    pmtiles = stage_basemap(OUTPUT_DIR, settings.geodata_work_dir)
    heading(logger, f"Leyendo colonias y barrios (zoom {READ_ZOOM}; tarda unos minutos)")
    target = PostgresTarget(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )
    summary = load_places(engine, target, pmtiles)
    heading(
        logger,
        f"Listo: {summary.loaded:,} de {summary.read:,} lugares dentro de México "
        f"({', '.join(f'{k} {v:,}' for k, v in summary.by_kind.items())})",
    )
    show_samples(engine)


if __name__ == "__main__":
    main()
