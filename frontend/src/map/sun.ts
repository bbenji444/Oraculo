/**
 * El Sol en su posición real, para iluminar el globo (rediseño del 26/10/2026).
 *
 * La atmósfera del globo de MapLibre es un modelo físico de dispersión de la
 * luz: brilla azul del lado de día, se tiñe en el borde entre el día y la
 * noche y se apaga del lado de noche, según la posición de `light`. Aquí se
 * calcula dónde está el Sol (el punto de la Tierra donde está en el cenit) y
 * se traduce:
 *
 * - a `light.position` de MapLibre (anclada al mapa, ver `getSunPos` en
 *   maplibre-gl 6: gira la luz con el centro del mapa);
 * - a una dirección en el cielo de `SpaceBackground`, para dibujar el brillo
 *   del Sol detrás del globo con la misma orientación que las estrellas.
 *
 * Precisión: unas décimas de grado (fórmula de la declinación por día del año
 * y la ecuación del tiempo de la NOAA). Para un efecto visual, sobra.
 *
 * No hace: no dibuja nada.
 */

const DEG = Math.PI / 180;
const MS_PER_DAY = 86_400_000;
const MINUTES_PER_DAY = 1440;
/** Inclinación del eje de la Tierra (grados). */
const AXIAL_TILT = 23.44;
/** La declinación es mínima ~10 días antes del 1 de enero (solsticio de diciembre). */
const SOLSTICE_OFFSET_DAYS = 10;
const DAYS_PER_YEAR = 365.24;
const DEGREES_PER_MINUTE = 0.25;
/** Distancia de la luz que usa MapLibre por defecto (`light.position[0]`). */
export const LIGHT_RADIUS = 1.15;

export interface SubsolarPoint {
  /** Latitud donde el Sol está en el cenit (grados, −23.44 a 23.44). */
  lat: number;
  /** Longitud (grados, −180 a 180). */
  lng: number;
}

/**
 * El punto de la Tierra donde el Sol está en el cenit en un momento.
 *
 * @example subsolarPoint(new Date('2026-06-21T12:00:00Z')) // ≈ { lat: 23.4, lng: -0.4 }
 */
export function subsolarPoint(date: Date): SubsolarPoint {
  const start = Date.UTC(date.getUTCFullYear(), 0, 0);
  const dayOfYear = (date.getTime() - start) / MS_PER_DAY;
  const lat =
    -AXIAL_TILT * Math.cos(((2 * Math.PI) / DAYS_PER_YEAR) * (dayOfYear + SOLSTICE_OFFSET_DAYS));
  // Ecuación del tiempo (minutos): el Sol se adelanta o atrasa al reloj.
  const b = ((2 * Math.PI) / DAYS_PER_YEAR) * (dayOfYear - 81);
  const equationOfTime = 9.87 * Math.sin(2 * b) - 7.53 * Math.cos(b) - 1.5 * Math.sin(b);
  const minutes =
    date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60 + equationOfTime;
  // A mediodía solar en Greenwich el Sol está sobre la longitud 0.
  let lng = -(minutes - MINUTES_PER_DAY / 2) * DEGREES_PER_MINUTE;
  lng = ((((lng + 180) % 360) + 360) % 360) - 180;
  return { lat, lng };
}

/**
 * La luz de MapLibre que pone al Sol sobre el punto subsolar.
 *
 * Con `anchor: 'map'`, MapLibre gira la luz con el centro del mapa, así que la
 * posición se mide desde el punto (0°, 0°): el ángulo polar es la distancia
 * angular al punto subsolar y el azimut, el rumbo hacia él (desde el norte,
 * en el sentido de las manecillas).
 *
 * @returns `[radio, azimut, polar]` en grados, como pide `light.position`.
 */
export function sunLightPosition(point: SubsolarPoint): [number, number, number] {
  const phi = point.lat * DEG;
  const lambda = point.lng * DEG;
  const polar = Math.acos(Math.cos(phi) * Math.cos(lambda)) / DEG;
  const azimuth = (Math.atan2(-Math.cos(phi) * Math.sin(lambda), Math.sin(phi)) / DEG + 360) % 360;
  return [LIGHT_RADIUS, azimuth, polar];
}

/**
 * Dirección del Sol en el cielo de `SpaceBackground` (vector unitario).
 *
 * Es el mismo marco que usan las estrellas (`starCameraRotation`): X hacia la
 * longitud 90° E, Y hacia el norte y Z hacia el punto (0°, 0°).
 */
export function sunSkyDirection(point: SubsolarPoint): { x: number; y: number; z: number } {
  const phi = point.lat * DEG;
  const lambda = point.lng * DEG;
  return {
    x: Math.cos(phi) * Math.sin(lambda),
    y: Math.sin(phi),
    z: Math.cos(phi) * Math.cos(lambda),
  };
}
