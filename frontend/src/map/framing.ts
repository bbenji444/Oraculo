/**
 * Encuadre de la cámara según el tamaño real de la pantalla (§14.2).
 *
 * Al volar a una región o a una nota, el globo deja libre lo que tapan los
 * paneles: en escritorio, el panel izquierdo (si está abierto) y los botones de
 * las esquinas; en celular, el botón flotante de arriba. Antes los márgenes eran
 * fijos y pensados para escritorio: en un celular de 375 px sumaban más que la
 * pantalla y MapLibre se negaba a volar ("Map cannot fit within canvas").
 *
 * Funciones puras: el componente del mapa solo las aplica.
 * No hace: no toca el mapa ni el DOM.
 */

export interface ScreenSize {
  width: number;
  height: number;
}

export interface FlyPadding {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

// Por debajo de este ancho el panel ocupa toda la pantalla (Tailwind `md`, igual
// que ExplorePage): se oculta al elegir una nota, así que no se descuenta.
export const NARROW_MAX_WIDTH = 767;
// Panel izquierdo abierto: 24 rem (384 px) + 16 px de margen + aire.
export const PANEL_CLEARANCE_PX = 430;
// Botones de acercar y alejar (arriba a la derecha) y controles de abajo.
export const DESKTOP_EDGE_PX = { top: 80, bottom: 100, side: 80 };
// En celular: el botón flotante "Búsqueda y noticias" arriba y aire a los lados.
export const NARROW_EDGE_PX = { top: 72, bottom: 48, side: 24 };
// Lo mínimo que debe quedar para dibujar la región; si los márgenes dejan
// menos, se reducen en proporción (MapLibre no vuela si no cabe).
export const MIN_FRAME_PX = 160;
// Nota elegida en escritorio: el punto queda a la izquierda y abajo del centro
// para que su ficha quepa a la derecha.
export const DESKTOP_ARTICLE_OFFSET: [number, number] = [-120, 70];
// En celular la ficha no cabe a un lado: el punto baja y la ficha va encima.
export const NARROW_ARTICLE_DROP = 0.22;
// Encuadre del globo según los paneles (Benji, 27/10/2026): con un panel a un
// lado, el centro de la cámara se corre a la parte libre; sin paneles, el
// globo se centra y crece un poco. Solo se agranda en la vista de globo: de
// cerca (una ciudad) solo se recentra.
export const GLOBE_FRAME_MAX_ZOOM = 3;
export const GLOBE_EXPAND_ZOOM = 0.18;
// Duración del corrimiento, en milisegundos: lo que tarda el panel en irse.
export const GLOBE_FRAME_MS = 900;
// Diseño «Centro de mando»: el globo se ajusta al espacio libre entre el
// encabezado y la consola. Ocupa todo el lado corto: su orilla y el halo pasan
// detrás del vidrio de la consola (antes 0.9; Benji lo pidió más grande el
// 27/10/2026) y su zoom se queda entre estos topes, para que no se
// vuelva una canica ni se salga de la pantalla.
export const GLOBE_FIT_SHARE = 1;
export const GLOBE_FIT_MIN_ZOOM = 1.1;
export const GLOBE_FIT_MAX_ZOOM = 2.4;
// Zoom al volar a una nota, según qué tan preciso es su lugar: siempre el
// mismo para la misma precisión (antes era "el mayor entre el actual y este" y,
// ya de cerca, elegir otra nota no acercaba nada). Benji pidió el 26/10/2026
// acercarse «casi casi al lugar de los hechos»: localidad o colonia a 14.5
// (se ven las calles), municipio a 11.5 (la ciudad y sus alrededores: el
// centro del municipio suele caer en el campo y a 12.5 no se veía nada),
// estado a 7 y país a 5.
export const ARTICLE_ZOOM: Record<'country' | 'state' | 'municipality' | 'locality', number> = {
  country: 5,
  state: 7,
  municipality: 11.5,
  locality: 14.5,
};
// Ancho preferido de la ficha de una nota.
export const CALLOUT_WIDTH = 330;
// Margen de la ficha a cada lado en pantallas más angostas que ella.
const CALLOUT_SIDE_MARGIN = 12;

/** Si la pantalla es angosta (celular): el panel la cubre completa. */
export function isNarrow(screen: ScreenSize): boolean {
  return screen.width <= NARROW_MAX_WIDTH;
}

/** Reduce dos márgenes opuestos en proporción para que quede `MIN_FRAME_PX`. */
function fit(a: number, b: number, total: number): [number, number] {
  const room = total - MIN_FRAME_PX;
  if (a + b <= room) return [a, b];
  const scale = Math.max(0, room) / (a + b);
  return [Math.floor(a * scale), Math.floor(b * scale)];
}

/**
 * Márgenes para `cameraForBounds` al volar a una región.
 *
 * @param screen Ancho y alto del mapa en píxeles.
 * @param panelOpen Si el panel izquierdo está abierto.
 * @returns Márgenes que siempre dejan al menos `MIN_FRAME_PX` libres en cada eje.
 *
 * @example
 *   flyPadding({ width: 1366, height: 650 }, true) // left 430, right 80
 *   flyPadding({ width: 375, height: 812 }, true)  // left 24, right 24
 */
export function flyPadding(screen: ScreenSize, panelOpen: boolean): FlyPadding {
  const narrow = isNarrow(screen);
  const edge = narrow ? NARROW_EDGE_PX : DESKTOP_EDGE_PX;
  const leftWanted = !narrow && panelOpen ? PANEL_CLEARANCE_PX : edge.side;
  const [left, right] = fit(leftWanted, edge.side, screen.width);
  const [top, bottom] = fit(edge.top, edge.bottom, screen.height);
  return { top, bottom, left, right };
}

/**
 * Desplazamiento del punto de una nota respecto al centro, para que su ficha
 * quepa: a un lado en escritorio, encima en celular.
 *
 * @param screen Ancho y alto del mapa en píxeles.
 * @returns `[x, y]` en píxeles para `flyTo({ offset })`.
 */
export function articleOffset(screen: ScreenSize): [number, number] {
  if (!isNarrow(screen)) return DESKTOP_ARTICLE_OFFSET;
  return [0, Math.round(screen.height * NARROW_ARTICLE_DROP)];
}

// El mapa de calles detallado solo cubre este rectángulo (el mismo MEXICO_BBOX de
// backend/app/geodata/mapa_base.py). Fuera, el del mundo llega a zoom 6 y sus
// etiquetas se ven hasta 7 (BASEMAP_SWITCH_ZOOM): más cerca el mapa queda vacío.
export const MEXICO_DETAIL_BBOX: Bbox = [-118.6, 14.3, -86.5, 32.9];
export const WORLD_DETAIL_MAX_ZOOM = 6.5;

/**
 * Zoom al volar a una nota.
 *
 * @param precision Precisión de su lugar; `unknown` se trata como estado.
 * @param lng Longitud de la nota.
 * @param lat Latitud de la nota.
 * @returns Zoom de destino, el mismo esté donde esté la cámara; fuera de México,
 *   nunca más cerca de lo que alcanza el mapa del mundo.
 */
export function articleZoom(precision: string, lng: number, lat: number): number {
  const zoom =
    precision in ARTICLE_ZOOM
      ? ARTICLE_ZOOM[precision as keyof typeof ARTICLE_ZOOM]
      : ARTICLE_ZOOM.state;
  const [west, south, east, north] = MEXICO_DETAIL_BBOX;
  const inMexico = lng >= west && lng <= east && lat >= south && lat <= north;
  return inMexico ? zoom : Math.min(zoom, WORLD_DETAIL_MAX_ZOOM);
}

/** Ancho de la ficha: el preferido, o lo que quepa en pantallas más angostas. */
export function calloutWidth(screen: ScreenSize): number {
  return Math.min(CALLOUT_WIDTH, Math.max(0, screen.width - 2 * CALLOUT_SIDE_MARGIN));
}

export type Bbox = [west: number, south: number, east: number, north: number];

export interface GlobeCamera {
  /** Punto que queda en el centro de la pantalla (no el de la región). */
  center: [lng: number, lat: number];
  zoom: number;
}

// Tamaño del mundo en píxeles a zoom 0 (teselas de 512 px en MapLibre).
const TILE_SIZE = 512;
// Puntos por borde del rectángulo: los bordes de latitud se curvan en el globo
// y con las esquinas solas se cortaría la región.
const EDGE_SAMPLES = 16;
// Zoom mínimo al encuadrar: el globo completo se ve a 1.2 en una laptop.
export const MIN_FRAME_ZOOM = 1.2;
// Vueltas de ajuste: al alejarse, la cámara se corre un poco y la región se ve
// de otro ángulo. Con 8 vueltas y 2 % de aire Canadá y Rusia ya caben (pruebas).
const FRAME_ITERATIONS = 8;
const FRAME_SHRINK_MARGIN = 0.98;
const DEGREES = Math.PI / 180;

/** Vista ortográfica de un punto desde `center`, en una esfera de radio 1. */
function orthographic(lng: number, lat: number, center: [number, number]): [number, number] {
  const [lng0, lat0] = center;
  const dLng = (lng - lng0) * DEGREES;
  const phi = lat * DEGREES;
  const phi0 = lat0 * DEGREES;
  const x = Math.cos(phi) * Math.sin(dLng);
  const y = Math.cos(phi0) * Math.sin(phi) - Math.sin(phi0) * Math.cos(phi) * Math.cos(dLng);
  const facing =
    Math.sin(phi0) * Math.sin(phi) + Math.cos(phi0) * Math.cos(phi) * Math.cos(dLng) >= 0;
  if (facing) return [x, y];
  // Del otro lado del globo: se cuenta en el borde visible, en su dirección.
  const length = Math.hypot(x, y) || 1;
  return [x / length, y / length];
}

/** Inversa de `orthographic`: el punto del globo que se ve en (x, y). */
function fromOrthographic(x: number, y: number, center: [number, number]): [number, number] {
  const rho = Math.hypot(x, y);
  if (rho < 1e-12) return center;
  const c = Math.asin(Math.min(1, rho));
  const phi0 = center[1] * DEGREES;
  const lat = Math.asin(Math.cos(c) * Math.sin(phi0) + (y * Math.sin(c) * Math.cos(phi0)) / rho);
  const lng =
    center[0] * DEGREES +
    Math.atan2(
      x * Math.sin(c),
      rho * Math.cos(phi0) * Math.cos(c) - y * Math.sin(phi0) * Math.sin(c),
    );
  return [normalizeLng(lng / DEGREES), lat / DEGREES];
}

function normalizeLng(lng: number): number {
  return ((((lng + 180) % 360) + 360) % 360) - 180;
}

/** Puntos de los cuatro bordes del rectángulo (el este puede pasar de 180). */
function edgePoints([west, south, east, north]: Bbox): [number, number][] {
  const eastUnwrapped = east < west ? east + 360 : east;
  const points: [number, number][] = [];
  for (let i = 0; i <= EDGE_SAMPLES; i += 1) {
    const t = i / EDGE_SAMPLES;
    const lng = west + (eastUnwrapped - west) * t;
    const lat = south + (north - south) * t;
    points.push([lng, south], [lng, north], [west, lat], [eastUnwrapped, lat]);
  }
  return points;
}

/** Extensión de los puntos vistos desde `center`: mínimo y máximo en x y en y. */
function extent(points: [number, number][], center: [number, number]) {
  const projected = points.map(([lng, lat]) => orthographic(lng, lat, center));
  const xs = projected.map(([x]) => x);
  const ys = projected.map(([, y]) => y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

/**
 * Puntos del globo a `distance` grados del centro, en `count` direcciones
 * parejas (la primera hacia el norte, luego en el sentido del reloj).
 *
 * Sirve para encontrar el borde del globo en pantalla: con la cámara inclinada
 * y en perspectiva ya no está a 90° del centro, así que se proyectan varios
 * anillos y se queda el más lejano de cada dirección.
 *
 * @param center Centro de la cámara `[lng, lat]`.
 * @param distance Distancia en grados sobre la esfera (0 a 180).
 * @param count Cuántos puntos.
 * @returns Los puntos `[lng, lat]`.
 */
export function ringAround(
  center: [number, number],
  distance: number,
  count: number,
): [number, number][] {
  const phi1 = center[1] * DEGREES;
  const delta = distance * DEGREES;
  return Array.from({ length: count }, (_, i) => {
    const theta = (2 * Math.PI * i) / count;
    const phi2 = Math.asin(
      Math.sin(phi1) * Math.cos(delta) + Math.cos(phi1) * Math.sin(delta) * Math.cos(theta),
    );
    const lambda = Math.atan2(
      Math.sin(theta) * Math.sin(delta) * Math.cos(phi1),
      Math.cos(delta) - Math.sin(phi1) * Math.sin(phi2),
    );
    return [normalizeLng(center[0] + lambda / DEGREES), phi2 / DEGREES];
  });
}

/**
 * Cuánto se ven la aureola y el brillo del Sol alrededor del globo: completos
 * con el globo entero en pantalla y se apagan al acercarse (ya no hay borde).
 *
 * @param zoom Zoom de MapLibre.
 * @returns De 0 (no se ven) a 1.
 */
export function auraOpacity(zoom: number): number {
  if (zoom <= AURA_FULL_ZOOM) return 1;
  if (zoom >= AURA_GONE_ZOOM) return 0;
  return (AURA_GONE_ZOOM - zoom) / (AURA_GONE_ZOOM - AURA_FULL_ZOOM);
}
// La aureola se ve completa hasta zoom 3 (el globo cabe) y se apaga en 4.5.
export const AURA_FULL_ZOOM = 3;
export const AURA_GONE_ZOOM = 4.5;

function radiusAt(zoom: number, lat: number): number {
  return (TILE_SIZE * 2 ** zoom) / (2 * Math.PI * Math.cos(lat * DEGREES));
}

/** Radio máximo para que una extensión (en radios) quepa en `room` píxeles. */
function radiusToFit(room: number, reach: number): number {
  return reach > 1e-9 ? Math.max(1, room) / reach : Number.POSITIVE_INFINITY;
}

/**
 * Cámara que encuadra un rectángulo en el globo, dentro del espacio libre.
 *
 * `cameraForBounds` de MapLibre encuadra como si el mapa fuera plano
 * (Mercator), donde los polos se estiran sin fin: Canadá (hasta 83° N)
 * quedaba centrado en el Ártico y alejado. Aquí se mide la región como se ve
 * en la esfera desde el punto que quedará al centro de la pantalla. En el
 * globo de MapLibre el radio en píxeles es `512·2^zoom / (2π·cos(latitud del
 * centro))` (medido en Explorar el 20/10/2026). La vista real tiene perspectiva
 * y los bordes se ven más chicos que en la ortográfica, así que siempre cabe.
 *
 * El espacio libre no está centrado (el panel tapa la izquierda): en lugar de
 * desplazar la imagen, se mueve la cámara para que la región quede al centro de
 * ese espacio. Desplazar la imagen hacía ver la región desde otro ángulo y
 * Canadá o Rusia se salían unos 30 px.
 *
 * @param bbox Rectángulo [oeste, sur, este, norte]; si el este es menor que el
 *   oeste, cruza el meridiano 180. Un punto (oeste = este) se acerca al zoom máximo.
 * @param screen Ancho y alto del mapa en píxeles.
 * @param padding Márgenes que tapan los paneles (`flyPadding`).
 * @param maxZoom Zoom máximo para el nivel de la región.
 * @returns Centro de la pantalla y zoom para `flyTo`.
 *
 * @example
 *   globeCamera([-105.7, 18.9, -101.5, 22.75], { width: 1920, height: 879 }, padding, 7)
 *   // zoom ≈ 6.9, como cameraForBounds en una región chica
 */
export function globeCamera(
  bbox: Bbox,
  screen: ScreenSize,
  padding: FlyPadding,
  maxZoom: number,
): GlobeCamera {
  const [west, south, east, north] = bbox;
  const eastUnwrapped = east < west ? east + 360 : east;
  const points = edgePoints(bbox);
  // Centro del espacio libre, en píxeles desde el centro de la pantalla.
  const freeX = (padding.left - padding.right) / 2;
  const freeY = (padding.top - padding.bottom) / 2;
  const halfWidth = screen.width / 2;
  const halfHeight = screen.height / 2;
  // 1. Centro de la región tal como se ve (los bordes de latitud alta se
  //    curvan hacia el polo, así que no es el centro del rectángulo).
  let region: [number, number] = [normalizeLng((west + eastUnwrapped) / 2), (south + north) / 2];
  const first = extent(points, region);
  region = fromOrthographic((first.minX + first.maxX) / 2, (first.minY + first.maxY) / 2, region);
  // 2. Radio para que quepa en el espacio libre, vista desde su centro.
  const box = extent(points, region);
  const clampRadius = (value: number, lat: number) =>
    Math.min(radiusAt(maxZoom, lat), Math.max(radiusAt(MIN_FRAME_ZOOM, lat), value));
  let radius = clampRadius(
    Math.min(
      radiusToFit((screen.width - padding.left - padding.right) / 2, Math.max(-box.minX, box.maxX)),
      radiusToFit(
        (screen.height - padding.top - padding.bottom) / 2,
        Math.max(-box.minY, box.maxY),
      ),
    ),
    region[1],
  );
  // 3. La cámara se corre para que la región quede en el centro del espacio
  //    libre. Vista desde ahí, la región se ve de otro ángulo y puede crecer
  //    un poco: si algún borde se sale, solo se aleja (nunca va y viene).
  let center = fromOrthographic(-freeX / radius, freeY / radius, region);
  for (let i = 0; i < FRAME_ITERATIONS; i += 1) {
    const seen = extent(points, center);
    const wanted = Math.min(
      radiusToFit(halfWidth - padding.right, seen.maxX),
      radiusToFit(halfWidth - padding.left, -seen.minX),
      radiusToFit(halfHeight - padding.top, seen.maxY),
      radiusToFit(halfHeight - padding.bottom, -seen.minY),
    );
    if (wanted >= radius) break;
    radius = clampRadius(wanted * FRAME_SHRINK_MARGIN, center[1]);
    center = fromOrthographic(-freeX / radius, freeY / radius, region);
  }
  const zoom = Math.log2((radius * 2 * Math.PI * Math.cos(center[1] * DEGREES)) / TILE_SIZE);
  return { center, zoom: Math.min(maxZoom, Math.max(MIN_FRAME_ZOOM, zoom)) };
}

/**
 * Zoom del globo al abrir o cerrar los paneles de los lados.
 *
 * Al quedar libre (sin paneles), la vista de globo se acerca
 * `GLOBE_EXPAND_ZOOM`; al volver un panel, se aleja lo mismo. `expanded`
 * recuerda si ya se acercó, para que abrir y cerrar varias veces no acumule.
 *
 * @param zoom Zoom actual.
 * @param open Si queda algún panel a un lado.
 * @param expanded Si el globo está acercado por no tener paneles.
 * @example frameZoom(1.8, false, false) // { zoom: 1.98, expanded: true }
 */
export function frameZoom(
  zoom: number,
  open: boolean,
  expanded: boolean,
): { zoom: number; expanded: boolean } {
  if (zoom >= GLOBE_FRAME_MAX_ZOOM) return { zoom, expanded: false };
  if (!open && !expanded) return { zoom: zoom + GLOBE_EXPAND_ZOOM, expanded: true };
  if (open && expanded) return { zoom: zoom - GLOBE_EXPAND_ZOOM, expanded: false };
  return { zoom, expanded };
}

/**
 * Zoom para que el globo entero quepa en el espacio libre (diseño «Centro de
 * mando»): el radio cambia al doble por cada punto de zoom, así que basta
 * comparar el radio de ahora con el que cabría.
 *
 * De cerca (una ciudad) no cambia nada: ahí no se ve el globo entero.
 *
 * @param zoom Zoom actual.
 * @param radiusPx Radio del globo en pantalla con ese zoom.
 * @param free Ancho y alto libres (sin encabezado, consola ni paneles).
 * @example fitZoom(1.8, 239, { width: 1280, height: 496 }) // ≈ 1.70
 */
export function fitZoom(zoom: number, radiusPx: number, free: ScreenSize): number {
  if (zoom >= GLOBE_FRAME_MAX_ZOOM || radiusPx <= 0) return zoom;
  const target = (Math.min(free.width, free.height) / 2) * GLOBE_FIT_SHARE;
  if (target <= 0) return zoom;
  const fitted = zoom + Math.log2(target / radiusPx);
  return Math.min(GLOBE_FIT_MAX_ZOOM, Math.max(GLOBE_FIT_MIN_ZOOM, fitted));
}

// Vista general del Centro de mando: de la consola de abajo solo se reserva
// esta parte de su alto. El globo crece y su orilla pasa por detrás del vidrio
// de la consola (Benji: «aunque tape un poquito el panel de abajo, que tenga
// un zoom mayor para dar más presencia», 27/10/2026). Al volar a una región o
// a una nota se usa el margen completo, para que nada quede tapado.
export const GLOBE_DOCK_OVERLAP = 0.35;

/**
 * Márgenes de la cámara en la vista general: los mismos, salvo el de abajo,
 * que se reduce a `GLOBE_DOCK_OVERLAP` del alto de la consola.
 *
 * @example overviewPadding({ left: 0, right: 0, top: 72, bottom: 200 }) // bottom 70
 */
export function overviewPadding<T extends { bottom: number }>(insets: T): T {
  return { ...insets, bottom: Math.round(insets.bottom * GLOBE_DOCK_OVERLAP) };
}
