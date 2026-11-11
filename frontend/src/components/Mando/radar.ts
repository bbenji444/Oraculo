/**
 * Geometría del radar de búsqueda sobre la zona buscada (Benji, 11/11/2026:
 * «si seleccionamos Chiapas, se hace zoom a Chiapas y ahí se enfoca el
 * radar»).
 *
 * Funciones puras: dónde va el radar en la pantalla según el rectángulo de
 * la región proyectado por el mapa, y dónde aparecen los ecos (las notas que
 * «detecta» mientras se busca).
 *
 * No hace: no toca el mapa ni el DOM.
 */

/** Rectángulo [oeste, sur, este, norte] en grados. */
export type Bbox = readonly [number, number, number, number];

export interface ScreenPoint {
  x: number;
  y: number;
}

export interface RadarGeometry {
  /** Centro del radar, en píxeles desde la esquina del mapa. */
  cx: number;
  cy: number;
  /** Radio del radar, en píxeles. */
  radius: number;
  /** Rectángulo de la región en pantalla (para las esquinas de «objetivo»). */
  box: { left: number; top: number; width: number; height: number };
}

// Un radar menor que esto no se lee; mayor que este tanto de la pantalla tapa todo.
export const MIN_RADIUS_PX = 70;
const MAX_RADIUS_SHARE = 0.42;
// Un poco más grande que la región: que la abarque con aire alrededor.
const RADIUS_PADDING = 1.15;

/**
 * Dónde va el radar: centrado en la región y del tamaño de su rectángulo.
 *
 * @param project Convierte [lng, lat] en píxeles (`map.project`).
 * @param bbox Rectángulo de la región (`focus_bbox`).
 * @param viewport Ancho y alto del mapa, para el tope del radio.
 *
 * @example radarGeometry(map.project, chiapas.focus_bbox, { width: 1200, height: 800 })
 */
export function radarGeometry(
  project: (lngLat: [number, number]) => ScreenPoint,
  bbox: Bbox,
  viewport: { width: number; height: number },
): RadarGeometry {
  const [west, south, east, north] = bbox;
  const corners = [
    project([west, north]),
    project([east, north]),
    project([east, south]),
    project([west, south]),
  ];
  const xs = corners.map((c) => c.x);
  const ys = corners.map((c) => c.y);
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  const center = project([(west + east) / 2, (south + north) / 2]);
  const half = (Math.max(right - left, bottom - top) / 2) * RADIUS_PADDING;
  const cap = Math.min(viewport.width, viewport.height) * MAX_RADIUS_SHARE;
  return {
    cx: center.x,
    cy: center.y,
    radius: Math.round(Math.min(Math.max(half, MIN_RADIUS_PX), Math.max(cap, MIN_RADIUS_PX))),
    box: { left, top, width: right - left, height: bottom - top },
  };
}

export interface Blip {
  /** Posición dentro del radar, en % del diámetro (0–100). */
  x: number;
  y: number;
  /** Retraso de su aparición, en segundos. */
  delay: number;
}

// Ángulo dorado: reparte los ecos parejo, sin amontonarlos ni repetir.
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
// Los ecos se quedan dentro del 85 % del radio, lejos del borde.
const BLIP_SPREAD = 0.85;
// Uno nuevo cada tanto, al ritmo del barrido.
const BLIP_STAGGER_S = 0.45;

/**
 * Dónde aparecen los ecos: siempre los mismos lugares para el mismo número,
 * así no saltan de un lado a otro cuando llegan notas nuevas.
 *
 * @example blips(3) // [{ x: 50, y: …, delay: 0 }, …]
 */
export function blips(count: number): Blip[] {
  return Array.from({ length: Math.max(0, count) }, (_, i) => {
    const r = Math.sqrt((i + 0.5) / Math.max(count, 1)) * BLIP_SPREAD * 50;
    const angle = i * GOLDEN_ANGLE;
    return {
      x: Math.round((50 + r * Math.cos(angle)) * 10) / 10,
      y: Math.round((50 + r * Math.sin(angle)) * 10) / 10,
      delay: Math.round(i * BLIP_STAGGER_S * 100) / 100,
    };
  });
}

/**
 * «19.43° N · 99.13° O»: el centro de la región, como lectura de coordenadas.
 */
export function coordinatesLabel(bbox: Bbox): string {
  const [west, south, east, north] = bbox;
  const lat = (south + north) / 2;
  const lng = (west + east) / 2;
  const ns = lat >= 0 ? 'N' : 'S';
  const eo = lng >= 0 ? 'E' : 'O';
  return `${Math.abs(lat).toFixed(2)}° ${ns} · ${Math.abs(lng).toFixed(2)}° ${eo}`;
}
