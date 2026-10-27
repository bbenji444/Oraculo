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

// 8K siempre que la tarjeta gráfica la acepte. Con el campo de visión del cielo
// (SKY_FIELD_OF_VIEW), la 4K cubre ~1,050 pixeles de ancho, así que en casi
// cualquier pantalla se amplía y se ve pixeleada (Benji, 26/10/2026). Antes
// también se pedía una pantalla grande, medida una sola vez al arrancar: si
// arrancaba con otra escala, se quedaba con la 4K.
export const HIGH_RES_MIN_TEXTURE = 8192;

/**
 * Campo de visión vertical de la cámara del cielo, en grados. Con 37° (el de
 * MapLibre) se veía una franja angosta del cielo, muy ampliada. Con 60° la
 * textura 8K queda casi a su tamaño real. Las estrellas se desplazan un poco
 * más lento que el globo al girar, y eso se lee como que están más lejos.
 */
export const SKY_FIELD_OF_VIEW = 60;

/**
 * Qué textura de estrellas cargar.
 *
 * @param maxTextureSize Máximo de la tarjeta gráfica (`renderer.capabilities`).
 * @returns La 8K si cabe en la tarjeta; si no, la 4K.
 */
export function starTextureFor(maxTextureSize: number): StarTexture {
  return maxTextureSize >= HIGH_RES_MIN_TEXTURE ? 'starmap_8k.jpg' : 'starmap_4k.jpg';
}

/**
 * Resolución del lienzo del fondo: la de la pantalla en este momento, con tope.
 *
 * Se vuelve a pedir en cada cambio de tamaño o de escala. Antes se leía una
 * sola vez al arrancar, y si arrancaba a 1× (otra pantalla u otro zoom) el
 * fondo se quedaba a 1× en una pantalla al 125 % y el navegador lo estiraba.
 *
 * @param devicePixelRatio `window.devicePixelRatio`.
 */
export function spacePixelRatio(devicePixelRatio: number): number {
  return Math.min(devicePixelRatio, SPACE_MAX_PIXEL_RATIO);
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

// Estrellas nítidas encima de la textura, que ya trae millones tenues.
export const STAR_COUNT = 3200;
// Tamaños en píxeles: la mayoría pequeñas y unas pocas brillantes. Menos de
// 1 px se dibujaba como un cuadrito que parpadeaba al moverse (26/10/2026).
export const STAR_MIN_SIZE = 1;
export const STAR_MAX_SIZE = 3.2;
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

// Titileo apenas perceptible, de 85 % a 100 % de brillo en ciclos de 2 a 5 s.
// En el espacio las estrellas no titilan; con más se veía de caricatura.
export const TWINKLE_MIN = 0.85;
// La textura de la NASA viene tenue: la mitad de sus píxeles tienen 8 de 255.
// Antes se multiplicaba todo por 1.9, y el negro se volvía una bruma granulada.
// Ahora se resta un punto negro (en luz lineal) y luego se aclara: el fondo
// queda negro y la Vía Láctea y las estrellas se ven más (medido el 26/10/2026
// sobre la 8K: percentil 50 = 8, 90 = 16, 99 = 24).
export const STARMAP_BLACK_POINT = 0.0025;
export const STARMAP_GAIN = 2.2;
// El fondo se dibuja a 30 cuadros por segundo: el titileo no necesita más y
// deja libre la tarjeta gráfica para el globo (meta de 60 fps, §14.2).
export const SPACE_FPS = 30;
// Resolución máxima del lienzo del fondo: en pantallas muy densas no se nota.
export const SPACE_MAX_PIXEL_RATIO = 1.5;
