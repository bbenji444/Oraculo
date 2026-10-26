/**
 * Cámara del muro (Fase 9.6, plan §9.5 "Cámara cinematográfica").
 *
 * - Al elegir un nodo, el globo "se recorre a la izquierda": se deja a la
 *   derecha el espacio del panel (`nodePadding`) y la cámara orbita despacio
 *   alrededor del nodo (`orbitBearing`).
 * - La URL del muro (`#/explorar?caso=<id>`) se puede compartir y recargar
 *   (`wallCaseFromHash`, `wallHash`).
 *
 * No hace: no mueve el mapa; son cálculos puros que usa `CaseWall`.
 */

// Grados por segundo de la órbita: una vuelta en 90 s, lenta para leer el
// panel sin marearse. Decisión de la 9.6.
export const ORBIT_DEGREES_PER_SECOND = 4;
// Ancho del panel lateral del muro (Tailwind `w-96`) y aire alrededor.
export const WALL_PANEL_WIDTH_PX = 384;
const PANEL_MARGIN_PX = 32;
// Zoom al elegir un nodo: se ven él y sus vecinos de la misma alcaldía.
export const NODE_ZOOM = 14.2;
// Inclinación al orbitar: suficiente para ver los arcos levantados.
export const ORBIT_PITCH = 50;
// Encuadre del caso completo: nunca más cerca que esto (un caso de un solo
// lugar no debe quedar a nivel calle).
export const WALL_MAX_ZOOM = 13.5;

/**
 * Rumbo de la cámara tras orbitar un tiempo, en el rango de MapLibre (−180, 180].
 *
 * @example orbitBearing(170, 5000) // 170 + 20 = 190 → −170
 */
export function orbitBearing(
  start: number,
  elapsedMs: number,
  degreesPerSecond = ORBIT_DEGREES_PER_SECOND,
): number {
  const turned = start + (degreesPerSecond * elapsedMs) / 1000;
  const normalized = ((turned % 360) + 360) % 360;
  return normalized > 180 ? normalized - 360 : normalized;
}

/** Márgenes para centrar un nodo dejando libre el panel de la derecha. */
export function nodePadding(screenWidth: number): {
  top: number;
  bottom: number;
  left: number;
  right: number;
} {
  // En pantallas angostas el panel va abajo y tapa todo el ancho: sin margen lateral.
  const right = screenWidth > WALL_PANEL_WIDTH_PX * 2 ? WALL_PANEL_WIDTH_PX + PANEL_MARGIN_PX : 0;
  return { top: 80, bottom: 80, left: 40, right };
}

const CASE_PARAM = 'caso';

/**
 * El caso cuyo muro pide la URL, si lo pide.
 *
 * @example wallCaseFromHash('#/explorar?caso=2d6f') // '2d6f'
 */
export function wallCaseFromHash(hash: string): string | null {
  const [path, query = ''] = hash.split('?');
  if (path !== '#/explorar') return null;
  const caseId = new URLSearchParams(query).get(CASE_PARAM);
  return caseId === null || caseId === '' ? null : caseId;
}

/** La URL del muro de un caso (o de Explorar sin muro). */
export function wallHash(caseId: string | null): string {
  return caseId === null ? '#/explorar' : `#/explorar?${CASE_PARAM}=${encodeURIComponent(caseId)}`;
}
