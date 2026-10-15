# geodata/

Pipeline de geodatos: descarga el Marco Geoestadístico de INEGI y Natural Earth, los valida, los carga a PostGIS a resolución completa y genera los PMTiles que ve el navegador (especificación, sección 12).

> **Se implementa en la Fase 1.** En la Fase 0 solo existe la estructura.

| Carpeta | Qué va ahí | ¿En git? |
|---|---|---|
| `raw/` | Descargas originales, con su URL, fecha y edición. | No (pesadas) |
| `scripts/` | Descarga, detección de encoding, reproyección, carga a PostGIS y generación de PMTiles. | Sí |
| `output/` | PMTiles generados. nginx los sirve en `/tiles/`. | No (se regeneran) |

Se ejecutará con `wsl make geo-load`. Corre en Ubuntu (WSL) porque tippecanoe, que genera los PMTiles, no existe para Windows ([ADR-0006](../docs/adr/0006-entorno-desarrollo-sin-docker.md)).
