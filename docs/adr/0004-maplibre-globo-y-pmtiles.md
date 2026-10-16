# ADR-0004 — MapLibre GL (globo) + PMTiles autoalojados

- **Estado:** aceptado
- **Fecha:** 2026-10-15
- **Fase:** F0

## Contexto

La pantalla principal es un globo 3D rotable que hace zoom continuo desde la vista mundial hasta municipios y localidades de México, con miles de polígonos INEGI, mapas de calor y marcadores agrupados.
Es un sistema institucional: no debe depender de servidores de mapas externos ni de llaves de pago, y debe sostener 60 fps al rotar en un equipo de oficina.

## Decisión

1. **MapLibre GL JS v5 con proyección `globe`** para el globo y el mapa. Es open source, sin llave ni costo, y la misma librería pasa del globo al detalle de calle ([ejemplo oficial de globo](https://maplibre.org/maplibre-gl-js/docs/examples/display-a-globe-with-a-vector-map/)).
2. **Teselas en archivos PMTiles autoalojados**: mapa base de Protomaps (OpenStreetMap) y capas INEGI propias. Un PMTiles es un solo archivo por capa que el navegador lee por partes con peticiones HTTP Range, sin servidor de teselas ([documentación de PMTiles](https://docs.protomaps.com/pmtiles/)). MapLibre lo lee con el plugin y protocolo oficial ([ejemplo](https://maplibre.org/maplibre-gl-js/docs/examples/pmtiles-source-and-protocol/)).
3. **nginx sirve los PMTiles** con soporte de Range, junto con el frontend.
4. Las geometrías al navegador **siempre** van por PMTiles simplificados por nivel de zoom; nunca se descargan GeoJSON pesados.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| CesiumJS | Excelente en 3D y terreno, pero más pesado; su ecosistema de teselas vectoriales y estilos es menos directo para mapas temáticos, y su servicio de datos (Cesium ion) empuja a una dependencia externa. |
| deck.gl | Muy bueno para capas de datos, pero necesita un mapa base aparte (normalmente MapLibre); agrega complejidad sin resolver el globo por sí solo. |
| react-globe.gl (three.js) | Muy vistoso a nivel mundial, pero no hace zoom continuo hasta municipios ni maneja teselas vectoriales. |
| Mapbox GL JS | Requiere llave y tiene costo por uso; licencia no libre desde la v2. |
| Servidor de teselas (Martin, TileServer GL) | Otro servicio que operar; PMTiles da lo mismo con un archivo estático. |

## Consecuencias

- Sin costos por uso de mapas ni dependencias externas en tiempo de ejecución.
- El pipeline de geodatos (F1) debe generar PMTiles con tippecanoe, que solo existe para Linux/macOS (en desarrollo corre en WSL, ADR-0006).
- Cada feature de las teselas lleva `code` y `name` para que un click resuelva la región sin consultar geometrías.
