/**
 * Todo el movimiento del globo en un solo lugar (ADR-0017, especificación §14.2).
 *
 * Funciones puras: cuánto dura un vuelo, con qué curva, cuánto se inclina la
 * cámara, cómo arranca la rotación y cuánto esperar entre los puntos que
 * aparecen. El componente del mapa solo las aplica. Cada constante lleva el
 * porqué de su valor (CLAUDE.md §5: sin números mágicos).
 *
 * No hace: no toca el mapa ni el DOM.
 */

/** Velocidad elegida por la persona (se recuerda en el navegador). */
export type MotionPreset = 'slow' | 'normal' | 'fast' | 'off';

export const MOTION_PRESETS: readonly MotionPreset[] = ['slow', 'normal', 'fast', 'off'];

export const MOTION_LABELS: Record<MotionPreset, string> = {
  slow: 'Lenta',
  normal: 'Normal',
  fast: 'Rápida',
  off: 'Sin animación',
};

// Multiplica la duración de vuelos y transiciones: "lenta" alarga un 60 % y
// "rápida" acorta un 40 %; con "sin animación" todo es instantáneo.
const DURATION_FACTOR: Record<MotionPreset, number> = { slow: 1.6, normal: 1, fast: 0.6, off: 0 };
// Multiplica la velocidad de rotación: al revés que la duración.
const SPIN_FACTOR: Record<MotionPreset, number> = { slow: 0.6, normal: 1, fast: 1.6, off: 0 };

/** Factor de duración del preset (0 = sin animación). */
export function durationFactor(preset: MotionPreset): number {
  return DURATION_FACTOR[preset];
}

/** Factor de velocidad de rotación del preset (0 = no gira). */
export function spinFactor(preset: MotionPreset): number {
  return SPIN_FACTOR[preset];
}

// --- Entrada ------------------------------------------------------------------

// La cámara arranca lejos (la Tierra pequeña en el espacio) y desplazada al
// este, y llega girando al Atlántico; de ahí sigue el giro normal (ExploreGlobe).
export const INTRO_FROM_ZOOM = 0.2;
export const INTRO_LNG_OFFSET_DEGREES = 80;
// ~3.5 s se siente como una llegada, no como una espera.
export const INTRO_DURATION_MS = 3500;

// --- Vuelos -------------------------------------------------------------------

/** Adónde vuela la cámara. */
export type FlyKind = 'region' | 'article' | 'up';

export interface CameraPoint {
  lng: number;
  lat: number;
  zoom: number;
}

// Duración = base + distancia + cambio de zoom, entre un mínimo y un máximo:
// un salto corto no se arrastra y uno al otro lado del mundo no es eterno.
export const FLY_BASE_MS = 900;
// 9 ms por grado de arco: de México a Europa (~85°) suma ~0.8 s.
export const FLY_MS_PER_DEGREE = 9;
// 350 ms por nivel de zoom: de país (4) a municipio (11) suma ~2.5 s.
export const FLY_MS_PER_ZOOM = 350;
export const FLY_MIN_MS = 1200;
export const FLY_MAX_MS = 4500;
// Subir por las migas de pan es "volver": más rápido que acercarse.
export const FLY_UP_FACTOR = 0.6;

const DEGREES_TO_RADIANS = Math.PI / 180;
const RADIANS_TO_DEGREES = 180 / Math.PI;

/**
 * Distancia en grados de arco entre dos puntos de la esfera (haversine).
 *
 * @example greatCircleDegrees({ lng: 0, lat: 0 }, { lng: 90, lat: 0 }) // 90
 */
export function greatCircleDegrees(
  a: { lng: number; lat: number },
  b: { lng: number; lat: number },
): number {
  const dLat = (b.lat - a.lat) * DEGREES_TO_RADIANS;
  const dLng = (b.lng - a.lng) * DEGREES_TO_RADIANS;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * DEGREES_TO_RADIANS) *
      Math.cos(b.lat * DEGREES_TO_RADIANS) *
      Math.sin(dLng / 2) ** 2;
  return 2 * Math.asin(Math.min(1, Math.sqrt(h))) * RADIANS_TO_DEGREES;
}

/**
 * Cuánto dura un vuelo de la cámara.
 *
 * @param from Dónde está la cámara.
 * @param to Adónde va.
 * @param kind Región, nota o subir de nivel.
 * @param preset Velocidad elegida.
 * @returns Milisegundos (0 con "sin animación").
 * @example flyDurationMs({ lng: -102, lat: 23, zoom: 2 }, { lng: -103, lat: 20, zoom: 7 }, 'region', 'normal') // ~2680
 */
export function flyDurationMs(
  from: CameraPoint,
  to: CameraPoint,
  kind: FlyKind,
  preset: MotionPreset,
): number {
  const factor = durationFactor(preset);
  if (factor === 0) return 0;
  const raw =
    FLY_BASE_MS +
    FLY_MS_PER_DEGREE * greatCircleDegrees(from, to) +
    FLY_MS_PER_ZOOM * Math.abs(to.zoom - from.zoom);
  const clamped = Math.min(FLY_MAX_MS, Math.max(FLY_MIN_MS, raw));
  return Math.round(clamped * (kind === 'up' ? FLY_UP_FACTOR : 1) * factor);
}

// Inclinación de la cámara al llegar: el país se ve de frente; un estado o un
// municipio, un poco de lado para dar relieve; una nota, como mirando el lugar.
export const PITCH_BY_TARGET = {
  country: 0,
  state: 20,
  municipality: 35,
  locality: 45,
  article: 45,
} as const;

export type PitchTarget = keyof typeof PITCH_BY_TARGET;

/** Inclinación (pitch) al llegar a un destino, en grados. */
export function flyPitch(target: PitchTarget): number {
  return PITCH_BY_TARGET[target];
}

/** Curva suave de entrada y salida (cúbica): para vuelos entre regiones. */
export function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2;
}

/** Curva que frena al final (quíntica): la entrada de la cámara "aterriza". */
export function easeOutQuint(t: number): number {
  return 1 - (1 - t) ** 5;
}

/** Curva que frena al final (cúbica), más suave que la quíntica: para el zoom de la entrada. */
export function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

/**
 * Avance del giro durante la entrada: arranca rápido y frena parejo hasta
 * llevar justo la velocidad del giro normal, así el giro sigue sin pausa.
 *
 * Antes la entrada frenaba casi a cero (quíntica) y el giro arrancaba desde el
 * 5 %: unos 4 s con el mundo casi quieto al abrir, que se sentían como si el
 * sistema se trabara (Benji, 27/10/2026). Es una parábola (frenado constante)
 * con pendiente final `endSlope`.
 *
 * @param t Avance del tiempo, de 0 a 1.
 * @param endSlope Velocidad al final, en «recorrido total por duración total»:
 *   la del giro × la duración ÷ los grados recorridos. Entre 0 y 2.
 * @returns Avance del recorrido, de 0 a 1.
 *
 * @example
 *   introSpin(1, 0.1) // 1: llega
 *   // y su pendiente en 1 es 0.1: sigue a la velocidad del giro.
 */
export function introSpin(t: number, endSlope: number): number {
  const slope = Math.min(2, Math.max(0, endSlope));
  const u = Math.min(1, Math.max(0, t));
  return (slope - 1) * u * u + (2 - slope) * u;
}

// --- Rotación -----------------------------------------------------------------

// Tras este tiempo sin tocar el mapa, el globo vuelve a girar solo.
export const IDLE_RESUME_MS = 25_000;
// La rotación arranca acelerando durante 2 s, sin saltos.
export const SPIN_RAMP_MS = 2000;

/**
 * Qué fracción de la velocidad de giro lleva, según el tiempo desde que arrancó.
 *
 * @param elapsedMs Milisegundos desde que se reanudó.
 * @returns De 0 a 1, con curva suave.
 */
export function spinRamp(elapsedMs: number): number {
  if (elapsedMs <= 0) return 0;
  if (elapsedMs >= SPIN_RAMP_MS) return 1;
  return easeInOutCubic(elapsedMs / SPIN_RAMP_MS);
}

// --- Resultados ---------------------------------------------------------------

// Los puntos aparecen uno tras otro (cascada): 30 ms entre cada uno, sin pasar
// de 1.5 s en total aunque haya muchos.
export const STAGGER_STEP_MS = 30;
export const STAGGER_MAX_MS = 1500;
// Brillo al pasar el cursor sobre un punto.
export const HOVER_GLOW_MS = 150;
// Un latido del punto elegido.
export const PULSE_PERIOD_MS = 1400;

/**
 * Cuándo aparece el punto ``index`` de ``total``.
 *
 * @returns Milisegundos de espera (0 con "sin animación").
 */
export function staggerDelayMs(index: number, total: number, preset: MotionPreset): number {
  if (durationFactor(preset) === 0 || total <= 1) return 0;
  const step = Math.min(STAGGER_STEP_MS, STAGGER_MAX_MS / (total - 1));
  return Math.round(index * step * durationFactor(preset));
}

/**
 * Fase del latido (0 a 1) en un instante: el punto crece y se desvanece.
 *
 * @param nowMs Tiempo actual (por ejemplo, ``performance.now()``).
 */
export function pulsePhase(nowMs: number): number {
  return (nowMs % PULSE_PERIOD_MS) / PULSE_PERIOD_MS;
}
