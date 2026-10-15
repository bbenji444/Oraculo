# geodata/

Pipeline de geodatos: descarga el Marco Geoestadístico de INEGI y los países de Natural Earth, los revisa, los carga a PostGIS a resolución completa y genera los PMTiles que ve el navegador (especificación §12, [ADR-0008](../docs/adr/0008-fuentes-y-procesamiento-de-geodatos.md)).

La lógica vive en [`backend/app/geodata/`](../backend/app/geodata/), donde se prueba y se revisan sus tipos igual que el resto del backend. Aquí solo quedan los datos y los scripts que no son Python.

| Carpeta | Qué va ahí | ¿En git? |
|---|---|---|
| `raw/` | Descargas originales y `MANIFIESTO.json` (URL, edición, fecha, tamaño y SHA-256 de cada archivo). | No (pesadas) |
| `scripts/` | Scripts que no son Python (mapa base). | Sí |
| `output/` | PMTiles generados. nginx los sirve en `/tiles/`. | No (se regeneran) |

## Pasos

| Comando | Qué hace |
|---|---|
| `wsl make geo-download` | Descarga las fuentes a `raw/`. De INEGI baja **solo** el marco integrado nacional (≈249 MB) de dentro del ZIP de 2.9 GB, leyendo por partes (HTTP Range) y verificando el CRC. Si ya está descargado y su SHA-256 coincide, no lo vuelve a bajar. |

## Fuentes y licencias

| Fuente | Edición | Licencia |
|---|---|---|
| INEGI — Marco Geoestadístico, Encuesta Intercensal 2025 | 2026 (cobertura 2025-07-31 a 2025-11-14) | Términos de Libre Uso de la Información del INEGI: se debe citar la fuente. |
| Natural Earth — Admin 0 Countries 1:10m | publicado 2022-05-13 | Dominio público. |

Cualquier mapa o reporte que use estos datos debe citar: **© INEGI, Natural Earth**.
