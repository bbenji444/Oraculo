"""Fuentes de geodatos: de dónde se descargan y dónde se guardan.

Para cambiar a una edición nueva de INEGI basta con actualizar ``INEGI_MG``
(URL, miembro y edición) y volver a correr ``make geo-load`` (ADR-0008).

No hace: no descarga nada; solo describe las fuentes.
"""

from dataclasses import dataclass
from pathlib import Path

# backend/app/geodata/fuentes.py → la raíz del repositorio está 3 niveles arriba.
REPO_ROOT = Path(__file__).resolve().parents[3]
# Descargas originales (en .gitignore): geodata/raw/.
RAW_DIR = REPO_ROOT / "geodata" / "raw"
# Manifiesto con URL, edición, fecha, tamaño y SHA-256 de cada descarga.
MANIFEST_PATH = RAW_DIR / "MANIFIESTO.json"


@dataclass(frozen=True, slots=True)
class Source:
    """Una fuente de geodatos descargable.

    Attributes:
        key: Identificador estable, usado en el manifiesto.
        title: Nombre legible de la fuente y su edición.
        url: Dirección del archivo remoto.
        member: Si no es ``None``, solo se descarga este archivo de dentro
            del ZIP remoto (leyendo por partes con HTTP Range).
        edition: Edición o fecha de publicación de la fuente.
        relative_path: Dónde se guarda, relativo a ``RAW_DIR``.
        license: Términos de uso que obligan a citar la fuente.
    """

    key: str
    title: str
    url: str
    member: str | None
    edition: str
    relative_path: str
    license: str


INEGI_MG = Source(
    key="inegi_mg_integrado",
    title="INEGI — Marco Geoestadístico, Encuesta Intercensal 2025 (integrado nacional)",
    url=(
        "https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/"
        "bvinegi/productos/geografia/marcogeo/794551196649_s.zip"
    ),
    # El ZIP nacional (2.9 GB) trae 32 ZIPs por estado y este integrado
    # nacional (256 MB comprimido), que es el único que se necesita.
    member="MG_Integrado_Encuesta_Intercensal_2025.zip",
    edition="2026 (cobertura 2025-07-31 a 2025-11-14)",
    relative_path="inegi/MG_Integrado_Encuesta_Intercensal_2025.zip",
    license="Términos de Libre Uso de la Información del INEGI (citar la fuente)",
)

NATURAL_EARTH_COUNTRIES = Source(
    key="natural_earth_countries",
    title="Natural Earth — Admin 0 Countries 1:10m",
    url="https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
    member=None,
    # Fecha Last-Modified que reporta el servidor de Natural Earth.
    edition="publicado 2022-05-13",
    relative_path="natural_earth/ne_10m_admin_0_countries.zip",
    license="Dominio público",
)

ALL_SOURCES: tuple[Source, ...] = (INEGI_MG, NATURAL_EARTH_COUNTRIES)

# Capas del Marco Geoestadístico que se usan (dentro de conjunto_de_datos/),
# verificadas en la edición 2026. La capa 00a (AGEB, 213 MB) no se extrae.
INEGI_LAYERS: dict[str, str] = {
    "00ent": "estados",
    "00mun": "municipios",
    "00l": "localidades con polígono (urbanas y rurales amanzanadas)",
    "00lpr": "localidades rurales puntuales",
}
INEGI_DATA_DIR = "conjunto_de_datos"
# Extensiones de un shapefile que hacen falta para cargarlo.
SHAPEFILE_PARTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")
# Catálogo oficial de municipios de la edición, para validar el conteo (§12).
INEGI_MUNICIPAL_CATALOG_SUFFIX = "municipales.csv"
INEGI_CODE_FIELD = "CVEGEO"
INEGI_NAME_FIELD = "NOMGEO"
# Subcarpetas dentro de GEODATA_WORK_DIR (disco de Linux, ADR-0008) donde se
# extraen las capas: GDAL nunca lee directamente de /mnt/d.
INEGI_WORK_SUBDIR = "inegi"
NATURAL_EARTH_WORK_SUBDIR = "natural_earth"
NATURAL_EARTH_LAYER = "ne_10m_admin_0_countries"
# Lista curada de alias (ADR-0008), versionada en el repositorio.
ALIASES_PATH = REPO_ROOT / "geodata" / "aliases.csv"
# Resultado de la inspección (encoding y proyección), que usa el cargador.
INSPECTION_PATH = RAW_DIR / "inegi" / "INSPECCION.json"
