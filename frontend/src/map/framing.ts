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

/** Ancho de la ficha: el preferido, o lo que quepa en pantallas más angostas. */
export function calloutWidth(screen: ScreenSize): number {
  return Math.min(CALLOUT_WIDTH, Math.max(0, screen.width - 2 * CALLOUT_SIDE_MARGIN));
}
