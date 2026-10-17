/**
 * Cálculos del fondo de universo (ADR-0017): hacia dónde mira la cámara de las
 * estrellas, qué textura usar según el equipo y las estrellas propias que
 * titilan.
 *
 * Funciones puras (sin three.js ni DOM) para probarlas; el componente
 * `SpaceBackground` las aplica.
 */

/** Lo que el fondo necesita saber de la cámara del mapa. */
export interface CameraView {
  lng: number;
  lat: number;
  zoom: number;
  bearing: number;
  pitch: number;
}

const DEGREES_TO_RADIANS = Math.PI / 180;

/**
 * Giro de la cámara de las estrellas para una vista del mapa.
 *
 * Las estrellas están "en el infinito": al rodear la Tierra, el cielo gira con
 * la cámara. Se usa la misma rotación que la vista (longitud = giro
 * horizontal, latitud e inclinación = giro vertical, rumbo = ladeo), así el
 * universo acompaña al globo y se siente en 3D.
 *
 * @returns Ángulos en radianes para `camera.rotation` con orden `YXZ`.
 */
export function starCameraRotation(view: CameraView): { x: number; y: number; z: number } {
  return {
    y: view.lng * DEGREES_TO_RADIANS,
    x: (view.pitch - view.lat) * DEGREES_TO_RADIANS,
    z: view.bearing * DEGREES_TO_RADIANS,
  };
}

/** Textura de estrellas disponible (ADR-0017). */
export type StarTexture = 'starmap_4k.jpg' | 'starmap_8k.jpg';

// 8K solo si la tarjeta gráfica la acepta y la pantalla tiene al menos ~2.5K
// píxeles de ancho reales: en una pantalla común no se nota y cuesta memoria.
export const HIGH_RES_MIN_TEXTURE = 8192;
export const HIGH_RES_MIN_SCREEN_PX = 2560;

/**
 * Qué textura de estrellas cargar.
 *
 * @param maxTextureSize Máximo de la tarjeta gráfica (`renderer.capabilities`).
 * @param screenPixels Ancho de la pantalla en píxeles reales.
 */
export function starTextureFor(maxTextureSize: number, screenPixels: number): StarTexture {
  return maxTextureSize >= HIGH_RES_MIN_TEXTURE && screenPixels >= HIGH_RES_MIN_SCREEN_PX
    ? 'starmap_8k.jpg'
    : 'starmap_4k.jpg';
}

/** Una estrella propia (nítida, encima de la textura). */
export interface Star {
  /** Dirección unitaria en el cielo. */
  x: number;
  y: number;
  z: number;
  /** Tamaño en píxeles. */
  size: number;
  /** Desfase del titileo (0 a 2π). */
  phase: number;
  /** Color: 0 azulado, 0.5 blanco, 1 amarillento. */
  tint: number;
}

// Pocas estrellas nítidas alcanzan: la textura ya trae millones tenues.
export const STAR_COUNT = 2400;
// Tamaños en píxeles: la mayoría pequeñas, unas pocas brillantes.
export const STAR_MIN_SIZE = 0.6;
export const STAR_MAX_SIZE = 2.4;
// Exponente que hace raras a las estrellas grandes (distribución sesgada).
const STAR_SIZE_SKEW = 3;

/**
 * Generador pseudoaleatorio con semilla (mulberry32): siempre las mismas
 * estrellas, así el cielo no cambia al recargar y se puede probar.
 */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Estrellas repartidas de forma pareja por todo el cielo.
 *
 * @param count Cuántas.
 * @param seed Semilla.
 */
export function makeStars(count: number = STAR_COUNT, seed = 20261017): Star[] {
  const random = seededRandom(seed);
  return Array.from({ length: count }, () => {
    // Coseno de la latitud uniforme: reparto parejo en la esfera (sin
    // amontonarse en los polos).
    const z = random() * 2 - 1;
    const angle = random() * 2 * Math.PI;
    const ring = Math.sqrt(1 - z * z);
    return {
      x: ring * Math.cos(angle),
      y: ring * Math.sin(angle),
      z,
      size: STAR_MIN_SIZE + (STAR_MAX_SIZE - STAR_MIN_SIZE) * random() ** STAR_SIZE_SKEW,
      phase: random() * 2 * Math.PI,
      tint: random(),
    };
  });
}

// El titileo es lento y suave: un ciclo de 2 a 5 s, entre 65 % y 100 % de brillo.
export const TWINKLE_MIN = 0.65;
// Brillo de la textura de la NASA: viene tenue (la Vía Láctea casi no se ve en
// la muestra del 17/10/2026); 1.9 la hace visible sin quemar las estrellas.
export const STARMAP_EXPOSURE = 1.9;
// El fondo se dibuja a 30 cuadros por segundo: el titileo no necesita más y
// deja libre la tarjeta gráfica para el globo (meta de 60 fps, §14.2).
export const SPACE_FPS = 30;
// Resolución máxima del lienzo del fondo: en pantallas muy densas no se nota.
export const SPACE_MAX_PIXEL_RATIO = 1.5;
