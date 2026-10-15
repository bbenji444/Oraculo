"""Inspección de los geodatos descargados, antes de cargar nada.

Responde, con los datos reales, las preguntas que CLAUDE.md §6.4 y §2.6
exigen antes de procesar: ¿qué proyección traen?, ¿en qué encoding están los
nombres?, ¿cuántos registros hay?, y muestra 5 nombres reales con Ñ y
acentos para que una persona confirme que se leen bien.

No hace: no carga nada a la base de datos (eso es ``cargar``).
"""

import csv
import io
import subprocess
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.geodata import dbf
from app.geodata.encoding import EncodingReport, detect_encoding

# Herramienta de GDAL que identifica el código EPSG de un archivo .prj.
_GDALSRSINFO = "gdalsrsinfo"
# Tiempo máximo para llamar a gdalsrsinfo (es instantáneo; 30 s es de sobra).
_GDAL_TIMEOUT_SECONDS = 30
# Letras que hacen un buen ejemplo para revisar el encoding.
_ENIE = "ñÑ"
_ACCENTED = "áéíóúüÁÉÍÓÚÜ"
# Catálogo municipal: columnas clave de estado (0), nombre (1), clave de
# municipio (2) y nombre (3). Las claves INEGI tienen 2 y 3 dígitos.
_CATALOG_MIN_COLUMNS = 4
_STATE_CODE_DIGITS = 2
_MUN_CODE_DIGITS = 3
# De los 5 ejemplos, al menos 2 con acentos (sin Ñ) para revisar ambos casos.
_ACCENT_EXAMPLES = 2


class InspectionError(Exception):
    """Los geodatos no tienen la forma esperada (falta una capa, un campo...)."""


@dataclass(frozen=True, slots=True)
class ExtractionPlan:
    """Qué extraer del ZIP integrado de INEGI.

    Attributes:
        layers: Capas a extraer (``00ent``...).
        data_dir: Carpeta de las capas dentro del ZIP.
        parts: Extensiones de shapefile a extraer.
        catalog_suffix: Final del nombre del catálogo de municipios.
    """

    layers: tuple[str, ...]
    data_dir: str
    parts: tuple[str, ...]
    catalog_suffix: str

    @property
    def catalog_relative_path(self) -> str:
        """Dónde queda el catálogo extraído, con un nombre ASCII estable."""
        return f"catalogos/catalogo_municipal{Path(self.catalog_suffix).suffix}"


@dataclass(frozen=True, slots=True)
class NameExample:
    """Un nombre real con su clave y los bytes del carácter especial.

    Attributes:
        code: Clave INEGI (CVEGEO).
        name: Nombre decodificado con el encoding elegido.
        raw_hex: Bytes crudos del nombre en hexadecimal, para ver la Ñ.
    """

    code: str
    name: str
    raw_hex: str


@dataclass(frozen=True, slots=True)
class LayerInspection:
    """Resultado de inspeccionar una capa.

    Attributes:
        layer: Nombre de la capa (``00mun``).
        description: Qué contiene.
        record_count: Número de registros.
        fields: Campos del DBF.
        epsg: Código EPSG detectado a partir del ``.prj``.
        encoding: Decisión de encoding con su evidencia.
        duplicate_codes: Claves repetidas (deben ser 0).
    """

    layer: str
    description: str
    record_count: int
    fields: tuple[str, ...]
    epsg: str
    encoding: EncodingReport
    duplicate_codes: int


def extract_layers(zip_path: Path, destination: Path, plan: ExtractionPlan) -> list[Path]:
    """Extrae del ZIP solo los archivos de las capas que se usan y el catálogo.

    Si un archivo ya está extraído con el mismo tamaño, no se vuelve a escribir.

    Args:
        zip_path: ZIP integrado de INEGI.
        destination: Carpeta de destino.
        plan: Capas, partes y catálogo a extraer.

    Returns:
        Las rutas extraídas.

    Raises:
        InspectionError: Si falta alguna parte de una capa o el catálogo.
    """
    wanted = {f"{plan.data_dir}/{layer}{ext}" for layer in plan.layers for ext in plan.parts}
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        missing = sorted(wanted - names)
        if missing:
            raise InspectionError(f"Al ZIP le faltan archivos: {', '.join(missing)}")
        catalogs = [n for n in names if n.endswith(plan.catalog_suffix)]
        if len(catalogs) != 1:
            raise InspectionError(f"No se encontró un único catálogo '*{plan.catalog_suffix}'.")
        for info in zf.infolist():
            if info.filename not in wanted and info.filename != catalogs[0]:
                continue
            # El nombre del catálogo trae acentos en un encoding de DOS; se
            # guarda con un nombre ASCII estable para no depender de eso.
            relative = plan.catalog_relative_path if info.filename == catalogs[0] else info.filename
            target = destination / relative
            if not (target.exists() and target.stat().st_size == info.file_size):
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, target.open("wb") as out:
                    while block := source.read(1024 * 1024):
                        out.write(block)
            extracted.append(target)
    return extracted


def detect_epsg(prj_path: Path) -> str:
    """Identifica el código EPSG de un archivo ``.prj`` con GDAL.

    Args:
        prj_path: Ruta del ``.prj``.

    Returns:
        Por ejemplo ``EPSG:6372``.

    Raises:
        InspectionError: Si GDAL no lo reconoce como un código EPSG.
    """
    result = subprocess.run(  # noqa: S603 — comando fijo de GDAL con una ruta local
        [_GDALSRSINFO, "-o", "epsg", str(prj_path)],
        capture_output=True,
        text=True,
        timeout=_GDAL_TIMEOUT_SECONDS,
        check=False,
    )
    for line in result.stdout.splitlines():
        if line.strip().upper().startswith("EPSG:"):
            return line.strip().upper()
    raise InspectionError(
        f"GDAL no identificó un código EPSG para {prj_path.name}: {result.stdout.strip()}"
    )


def inspect_layer(shp_dir: Path, layer: str, description: str) -> LayerInspection:
    """Inspecciona una capa: registros, campos, proyección, encoding y claves.

    Args:
        shp_dir: Carpeta con los archivos de la capa.
        layer: Nombre de la capa.
        description: Qué contiene, para el reporte.

    Returns:
        El resultado de la inspección.
    """
    dbf_path = shp_dir / f"{layer}.dbf"
    header = dbf.read_header(dbf_path)
    rows = list(dbf.iter_raw_values(dbf_path, ("CVEGEO", "NOMGEO")))
    codes = [code for code, _ in rows]
    cpg_path = shp_dir / f"{layer}.cpg"
    declared = cpg_path.read_text(encoding="ascii").strip() if cpg_path.exists() else None
    return LayerInspection(
        layer=layer,
        description=description,
        record_count=len(rows),
        fields=tuple(f.name for f in header.fields),
        epsg=detect_epsg(shp_dir / f"{layer}.prj"),
        encoding=detect_encoding((name for _, name in rows), declared),
        duplicate_codes=len(codes) - len(set(codes)),
    )


def pick_examples(
    rows: Iterable[tuple[bytes, ...]], encoding: str, count: int
) -> list[NameExample]:
    """Elige nombres reales que sirvan para revisar el encoding a ojo.

    Busca sobre todo nombres con Ñ (la letra que más se rompe) y completa con
    nombres con acentos o diéresis, sin repetir.

    Args:
        rows: Tuplas (clave, nombre) en bytes crudos.
        encoding: Encoding con el que se decodifican.
        count: Cuántos ejemplos devolver.

    Returns:
        Hasta ``count`` ejemplos: primero los que tienen Ñ.
    """
    with_enie: list[NameExample] = []
    with_accent: list[NameExample] = []
    seen: set[str] = set()
    for row in rows:
        raw_code, raw_name = row[0], row[1]
        name = raw_name.decode(encoding)
        if name in seen:
            continue
        example = NameExample(raw_code.decode("ascii"), name, raw_name.hex(" "))
        if any(c in _ENIE for c in name):
            with_enie.append(example)
        elif any(c in _ACCENTED for c in name):
            with_accent.append(example)
        else:
            continue
        seen.add(name)
        if len(with_enie) >= count and len(with_accent) >= count:
            break
    enie_quota = min(len(with_enie), count - _ACCENT_EXAMPLES)
    return (with_enie[:enie_quota] + with_accent + with_enie[enie_quota:])[:count]


def read_catalog_codes(csv_path: Path) -> tuple[set[str], str]:
    """Lee las claves municipales (CVEGEO de 5 dígitos) del catálogo oficial.

    El CSV de INEGI trae líneas de título antes de la cabecera, así que no
    basta con contar filas: se toman solo las filas cuyas dos primeras
    claves son numéricas (estado y municipio) y se arma la clave completa.

    Args:
        csv_path: Ruta del CSV del catálogo.

    Returns:
        (claves CVEGEO de municipio, encoding detectado del CSV).
    """
    raw = csv_path.read_bytes()
    report = detect_encoding(raw.splitlines())
    codes: set[str] = set()
    for row in csv.reader(io.StringIO(raw.decode(report.chosen))):
        if len(row) < _CATALOG_MIN_COLUMNS:
            continue
        state, municipality = row[0].strip(), row[2].strip()
        if state.isdigit() and municipality.isdigit():
            codes.add(state.zfill(_STATE_CODE_DIGITS) + municipality.zfill(_MUN_CODE_DIGITS))
    return codes, report.chosen
