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

- **Peso:** se estimaban ~60–110 MB de teselas. Medido al generarlas: 12.5 MB de día y 6.1 MB de noche (WebP, zoom 0–6), más 2.3 MB y 7.2 MB de los mapas de estrellas de 4K y 8K. Si algún día pasara de 150 MB, el zoom 6 se limitaría a México.
- **Nitidez:** a zoom 6, la textura de día viene de una imagen de ~2 km/píxel, aceptable. Para ver más detalle está el mapa vectorial, que aparece al acercarse.
- **Rendimiento:** hay dos lienzos WebGL en pantalla (mapa y fondo). El fondo solo dibuja cuando cambia la vista, para sostener la meta de 60 fps (§14.2).
  - **Medición del 17/10/2026** (navegador integrado, GPU Intel UHD integrada, monitor de 144 Hz, lienzo de 1280×884):
    - giro del globo en reposo: mediana de **~69 fps**, que cumple la meta;
    - vuelo de México a un estado con inclinación: **~48 fps** (un cuadro cada 20.8 ms, la mediana). MapLibre dibuja cada cuadro en ~6 ms (mediana), así que el límite está en la GPU.
  - Apagar la atmósfera, el fondo espacial o el desenfoque de los paneles no cambió el vuelo de forma repetible.
  - A 144 Hz, un cuadro que tarda entre 14 y 21 ms se muestra a 20.8 ms. En un monitor de 60 Hz ese mismo cuadro cabe en 16.7 ms, pero no se midió.
  - Si los analistas notan tirones, lo siguiente a probar es reducir la resolución del lienzo del mapa (`pixelRatio`) durante los vuelos.
- **Licencias:** la NASA pide crédito y se muestra en el mapa. El paquete de estrellas acredita además a Gaia/ESA solo en su versión 2020, que no se usa.

## Ajuste: fondo sin pixelear (26/10/2026)

Benji vio el fondo «muy pixeleado». Había tres causas:

1. **La cámara del cielo veía una franja angosta (37°).** Con la textura 4K, cada pixel de la foto ocupaba unos 2.2 pixeles de pantalla. Medido en un lienzo de 1,917 px de ancho: 887 pixeles de la textura repartidos en 1,917.
2. **La 8K solo cargaba en pantallas de 2,560 px reales o más**, así que casi nadie la veía.
3. **Toda la textura se multiplicaba por 1.9.** La mitad de sus pixeles valen 8 de 255, y eso volvía el negro una bruma granulada con el ruido del JPEG.

Cambios:

- **Campo de visión de 60°** (`SKY_FIELD_OF_VIEW`). Las estrellas se desplazan un poco más lento que el globo al girar, lo que se lee como que están más lejos.
- **8K desde 1,600 px reales.** Una laptop de 1366 px al 125 % ya la carga. Con eso, en el mismo lienzo hay unos 2,480 pixeles de la textura en 1,917 de pantalla (0.77, sin ampliar). Cuesta 7 MB de descarga, una sola vez, y unos 180 MB de memoria de video.
- **Punto negro y ganancia en luz lineal** (`STARMAP_BLACK_POINT` y `STARMAP_GAIN`) en lugar de multiplicar todo. El fondo queda negro y la Vía Láctea y las estrellas se aclaran.
- **Estrellas propias más reales:**
  - de 1 a 3.2 px, porque las de menos de 1 px parpadeaban como cuadritos;
  - un núcleo con un halo corto;
  - colores azulados, blancos y cálidos, y las más chicas más tenues;
  - un titileo casi nulo (85–100 %), porque en el espacio las estrellas no titilan.

**Corrección el mismo día.** Benji lo seguía viendo pixeleado. Medido en su pantalla al 125 %, el lienzo del fondo medía 1,534 px de ancho, y el del mapa 1,918, porque la escala y la textura se leían **una sola vez al arrancar**. Si la página arrancaba con otra escala (por emulación, otra pantalla o zoom), el fondo se quedaba a 1× con la 4K y el navegador lo estiraba. Ahora:

- la escala se vuelve a leer en cada cambio de tamaño y de resolución (`spacePixelRatio`, más `matchMedia`);
- el tamaño de las estrellas lo escala el shader;
- la 8K se usa siempre que la tarjeta la acepte, porque con 60° la 4K se amplía en casi cualquier pantalla.
