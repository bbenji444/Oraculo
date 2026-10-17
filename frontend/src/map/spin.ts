/**
 * Rotación automática del globo (especificación §14.2: "rotación lenta
 * automática centrada en México; se detiene al interactuar").
 *
 * Funciones puras, para probarlas sin mapa: cuántos grados avanza el globo
 * en cada paso según el zoom. El componente del mapa encadena los pasos con
 * `easeTo`. No toca el mapa ni el DOM.
 */

// Una vuelta completa cada 90 s: se nota que gira, sin distraer al leer.
export const SECONDS_PER_REVOLUTION = 90;
// Cada paso es una animación de 1 s; al terminar empieza la siguiente.
export const SPIN_STEP_MS = 1000;
// Desde este zoom ya se ve un país de cerca: girar estorbaría.
export const MAX_SPIN_ZOOM = 4;
// Entre este zoom y el máximo, el giro se frena poco a poco en vez de
// detenerse de golpe.
export const SLOW_SPIN_ZOOM = 3;

const DEGREES_PER_REVOLUTION = 360;
const MS_PER_SECOND = 1000;

/**
 * Grados de longitud que avanza el globo en un paso.
 *
 * @param zoom Zoom actual del mapa.
 * @param stepMs Duración del paso en milisegundos.
 * @returns Grados a desplazar hacia el oeste (0 si no debe girar).
 * @example spinDegrees(1.8) // 4
 */
export function spinDegrees(zoom: number, stepMs: number = SPIN_STEP_MS): number {
  if (zoom >= MAX_SPIN_ZOOM) return 0;
  const degrees = (DEGREES_PER_REVOLUTION / SECONDS_PER_REVOLUTION) * (stepMs / MS_PER_SECOND);
  if (zoom <= SLOW_SPIN_ZOOM) return degrees;
  return (degrees * (MAX_SPIN_ZOOM - zoom)) / (MAX_SPIN_ZOOM - SLOW_SPIN_ZOOM);
}

/**
 * Dice si la persona pidió a su sistema reducir animaciones (accesibilidad).
 * En ese caso el globo empieza quieto; el botón permite girarlo igual.
 *
 * @returns `true` si el sistema prefiere menos movimiento.
 */
export function prefersReducedMotion(): boolean {
  // globalThis es window en el navegador; así también funciona en las pruebas.
  const scope = globalThis as { matchMedia?: (query: string) => { matches: boolean } };
  if (typeof scope.matchMedia !== 'function') return false;
  return scope.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// Inclinación del eje de la Tierra respecto a su órbita (oblicuidad de la
// eclíptica, ~23.44°). Dibujar el globo con su polo norte inclinado lo hace
// verse como un globo terráqueo de escritorio.
export const EARTH_AXIAL_TILT_DEGREES = 23.44;
// Rumbo de la cámara en la vista de globo: negativo para que el polo norte
// se incline hacia la derecha, como en los globos de escritorio. El giro
// cambia la longitud, así que la Tierra rota alrededor de ese eje inclinado.
export const GLOBE_BEARING = -EARTH_AXIAL_TILT_DEGREES;
// Al acercarse a una región el mapa se endereza: así se lee con el norte arriba.
export const REGION_BEARING = 0;
