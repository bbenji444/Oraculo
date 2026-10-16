# geodata/

Pipeline de geodatos: descarga el Marco Geoestadístico de INEGI y los países de Natural Earth, los revisa, los carga a PostGIS a resolución completa y genera los PMTiles que ve el navegador (especificación §12, [ADR-0008](../docs/adr/0008-fuentes-y-procesamiento-de-geodatos.md)).

La lógica vive en [`backend/app/geodata/`](../backend/app/geodata/), donde se prueba y se revisan sus tipos igual que el resto del backend. Aquí solo quedan los datos y los scripts que no son Python.

| Carpeta | Qué va ahí | ¿En git? |
|---|---|---|
| `raw/` | Descargas originales y `MANIFIESTO.json` (URL, edición, fecha, tamaño y SHA-256 de cada archivo). | No (pesadas) |
| `aliases.csv` | Alias curados ("CDMX", "DF", "la capital del país"...) con que se **reconoce** un lugar en el texto de una nota: los usan el buscador de regiones y la geolocalización (F4). Revisados por una persona. | Sí |
| `search_terms.csv` | Palabras con que se **busca** un lugar en los proveedores de noticias, cuando no conviene su nombre oficial: el estado 15 se llama "México" y se busca como "Estado de México" o "Edomex" (ADR-0009). Las regiones que no aparecen se buscan por su nombre. | Sí |
| `output/` | PMTiles generados. nginx los sirve en `/tiles/`. | No (se regeneran) |

## Pasos

| Comando | Qué hace |
|---|---|
| `wsl make geo-download` | Descarga las fuentes a `raw/`. De INEGI baja **solo** el marco integrado nacional (≈249 MB) de dentro del ZIP de 2.9 GB, leyendo por partes (HTTP Range) y verificando el CRC. Si ya está descargado y su SHA-256 coincide, no lo vuelve a bajar. |
| `wsl make geo-inspect` | Extrae solo las capas que se usan (`00ent`, `00mun`, `00l`, `00lpr`) y el catálogo municipal. Reporta registros, campos, proyección (EPSG), encoding de los nombres con su evidencia y claves repetidas; compara las claves de municipios con el catálogo oficial; muestra 5 nombres reales con Ñ y acentos para revisión humana. Guarda la decisión en `raw/inegi/INSPECCION.json`. |
| `wsl make geo-load` | Carga a PostGIS lo inspeccionado (≈7 min), corre la validación y genera los PMTiles. Las capas se leen desde la carpeta de trabajo en el disco de Linux (`GEODATA_WORK_DIR`), nunca de `/mnt/d` (ADR-0008). Repetirla no duplica nada. |
| `wsl make geo-validate` | Criterios de aceptación de §12: 32 entidades, municipios = catálogo oficial (clave por clave), 16 alcaldías en la CDMX, 0 geometrías inválidas, nombres con Ñ idénticos al catálogo y el Zócalo en 09 / 09015; más revisiones extra (sin huérfanos, puntos dentro de su polígono, conteos de localidades). Termina con error si algo falla. |
| `wsl make geo-tiles` | Genera un PMTiles por capa con tippecanoe en la carpeta de trabajo y los copia verificados a `output/`: `countries` (z0–6), `states` (z2–10), `municipalities` (z5–14) y `localities` (puntos, z10–14). Cada figura lleva `id`, `code`, `name`, `display_prefix` y `level`; el `id` numérico permite resaltarla en el mapa. Verificado con `pmtiles verify`. |
| `wsl make geo-terms` | Aplica `search_terms.csv` y los códigos de país de Natural Earth (ISO-2 para SearchApi y Google News RSS; FIPS y nombre en inglés para GDELT) sin recargar geometrías: tarda segundos. `wsl make geo-terms ARGS=--muestra` enseña lo que aplicaría sin escribir nada. `geo-load` hace lo mismo al final. |
| `wsl make geo-basemap` | Recorta el mapa base de Protomaps (OpenStreetMap) de la construcción fijada `20261015`: el mundo hasta zoom 6 (43 MB) y México con sus islas hasta zoom 14, todas las calles (1.26 GB). Baja también las fuentes Noto Sans y el sprite `dark` de una versión fija de `basemaps-assets`, para no depender de servidores externos. Deja `output/MAPA_BASE.json` con versiones, tamaños y SHA-256; si ya está todo igual, no vuelve a bajar. |

## Cómo agregar un término de búsqueda

Cuando un lugar se escribe en los medios distinto a su nombre oficial (por ejemplo, "Tezoatlán" en lugar de "Heroica Villa Tezoatlán de Segura y Luna, Cuna de la Independencia de Oaxaca"):

1. Agrega una línea a `search_terms.csv` con la clave INEGI, el término y una nota del porqué. Si el lugar tiene términos, **reemplazan** a su nombre: incluye también el nombre oficial si sirve.
2. Corre `wsl make geo-terms ARGS=--muestra`, revisa y luego `wsl make geo-terms`.

## Fuentes y licencias

| Fuente | Edición | Licencia |
|---|---|---|
| INEGI — Marco Geoestadístico, Encuesta Intercensal 2025 | 2026 (cobertura 2025-07-31 a 2025-11-14) | Términos de Libre Uso de la Información del INEGI: se debe citar la fuente. |
| Natural Earth — Admin 0 Countries 1:10m | publicado 2022-05-13 | Dominio público. |
| Protomaps (datos de OpenStreetMap) | construcción 2026-10-15 | ODbL 1.0: se debe atribuir a los colaboradores de OpenStreetMap. Fuentes Noto Sans bajo OFL 1.1. |

Cualquier mapa o reporte que use estos datos debe citar: **© INEGI, Natural Earth, © colaboradores de OpenStreetMap, Protomaps**.
