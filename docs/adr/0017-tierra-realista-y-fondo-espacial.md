# ADR-0017 — Tierra realista, fondo espacial y movimiento del globo

- **Estado:** aceptado
- **Fecha:** 2026-10-17
- **Fase:** F6
- **Decide:** Benji
- **Complementa:** ADR-0004 (MapLibre, globo y PMTiles) y ADR-0007 (MapLibre v6)

## Contexto

Benji pidió para la Fase 6 una pantalla inmersiva:
- el globo domina la pantalla, sobre un fondo de universo con la Vía Láctea;
- la Tierra con textura realista (de noche, con las ciudades iluminadas);
- animaciones cuidadas al hacer clic, con velocidades moduladas.

Hasta F5 el globo usaba solo el mapa base vectorial oscuro de Protomaps y el halo atmosférico de MapLibre.

Verificado el 17/10/2026:

- **MapLibre 6.14:**
  - En proyección `globe`, el espacio alrededor del globo es transparente: se ve lo que haya detrás del lienzo ([guía de Stadia](https://docs.stadiamaps.com/tutorials/3d-globe-view-with-maplibre-gl-js/)).
  - `sky` ofrece `atmosphere-blend`, `sky-color` y `horizon-color` ([especificación](https://maplibre.org/maplibre-style-spec/sky/)), pero no tiene estrellas.
  - Las capas `raster` no tienen modos de mezcla: solo opacidad, brillo, contraste, saturación y tono.
- **Imágenes de la NASA** (uso libre con crédito; [política de Visible Earth](https://www.visibleearth.nasa.gov/image-use-policy)):

  | Imagen | Archivo | Tamaño |
  |---|---|---|
  | Blue Marble Next Generation (día), julio 2004, con relieve y batimetría | [`world.topo.bathy.200407.3x21600x10800.jpg`](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-topography-bathymetry/july/world.topo.bathy.200407.3x21600x10800.jpg) | 21600×10800, ~2 km/píxel |
  | Black Marble 2016 (luces nocturnas) | [`BlackMarble_2016_3km_geo.tif`](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/imagerecords/144000/144898/BlackMarble_2016_3km_geo.tif) | 13500×6750, 3 km/píxel |
  | Deep Star Maps (estrellas y Vía Láctea, coordenadas celestes) | [`starmap_4k.jpg` y `starmap_8k.jpg`](https://svs.gsfc.nasa.gov/3895) | 4096×2048 y 8192×4096 |

  El mapa de estrellas de 2020 (SVS 4851) solo viene en OpenEXR, y el GDAL de WSL no lee ese formato. Se usa el de 2012, que viene en JPG.
- **Herramientas en WSL:** GDAL 3.13 (escribe WebP y MBTiles; `gdal_calc.py` con numpy del sistema) y la CLI `pmtiles`.

## Decisión

1. **El globo sigue siendo MapLibre.** La Tierra realista son dos teselados raster locales:
   - **`earth_night.pmtiles` (por defecto):** Blue Marble oscurecido más las luces de Black Marble, sumadas píxel a píxel con `gdal_calc.py` (MapLibre no mezcla capas raster);
   - **`earth_day.pmtiles`:** Blue Marble tal cual.
   - Ambos en WebP, de zoom 0 a 6, generados con `make geo-earth`: descarga con manifiesto y SHA-256, MBTiles con GDAL, `pmtiles convert` y `pmtiles verify`. Nginx los sirve en `/tiles/` como el resto: nunca se piden a terceros.
   - De zoom 5 a 7 la textura se funde con el mapa vectorial de calles y con las capas de INEGI.
2. **Fondo de universo con three.js** en un lienzo detrás del mapa:
   - una esfera vista desde dentro con el mapa de estrellas (4K, u 8K si el equipo lo aguanta), más estrellas propias nítidas que titilan;
   - gira con la cámara del mapa con un poco de paralaje;
   - solo se dibuja mientras la cámara se mueve o mientras titila, y respeta "menos movimiento" del sistema.
3. **Todo el movimiento vive en `frontend/src/map/motion.ts`**, con constantes con nombre y pruebas:
   - entrada de la cámara;
   - vuelos con duración según la distancia;
   - rotación con rampa y reanudación tras inactividad;
   - presets de velocidad (lenta, normal, rápida y sin animación).
4. **Crédito visible en el mapa:** "Imágenes: NASA Earth Observatory · NASA SVS".

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| three.js cinematográfico (sombra día/noche, nubes, reflejo del mar) y MapLibre al acercarse | Dos motores sincronizados: más trabajo, más riesgo y menos fluidez en equipos de oficina. Benji eligió MapLibre + texturas. |
| CesiumJS | Biblioteca muy pesada. Sus imágenes por defecto dependen de una cuenta de Cesium ion. Habría que rehacer el clic en estados y municipios que ya funciona con PMTiles. |
| Pedir las imágenes a un servidor de teselas satelitales | Depende de terceros, de su cuenta y de su licencia (por ejemplo, Sentinel-2 cloudless es no comercial). La NASA es de uso libre. |
| Plugin `@geoql/maplibre-gl-starfield` | Versión 0.1.1, muy reciente y con poco uso. El fondo propio es poco código y se controla mejor. |

## Consecuencias

- **Peso:** ~60–110 MB más de teselas (se mide al generarlas). Si pasa de 150 MB, el zoom 6 se limita a México.
- **Nitidez:** a zoom 6, la textura de día viene de una imagen de ~2 km/píxel, aceptable. Para ver más detalle está el mapa vectorial, que aparece al acercarse.
- **Rendimiento:** hay dos lienzos WebGL en pantalla (mapa y fondo). El fondo solo dibuja cuando cambia la vista, para sostener la meta de 60 fps (§14.2).
- **Licencias:** la NASA pide crédito y se muestra en el mapa. El paquete de estrellas acredita además a Gaia/ESA solo en su versión 2020, que no se usa.
