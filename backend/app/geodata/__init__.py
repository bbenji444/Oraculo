"""Pipeline de geodatos de la especificación §12.

Pasos: descarga, inspección, carga a PostGIS, validación y generación de
PMTiles.

Es una entrada más del sistema, como ``api`` o ``worker``: usa el dominio
(``normalize_name``) y herramientas externas (GDAL, tippecanoe, pmtiles).
Cada paso se ejecuta con ``python -m app.geodata.<paso>`` desde los comandos
``make geo-*``. Las decisiones de fuentes y procesamiento están en ADR-0008.
"""
