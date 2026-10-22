/**
 * Geometría de los arcos de luz del muro (Fases 9.1 y 9.6, ADR-0102).
 *
 * Un arco sigue el gran círculo entre dos puntos del globo y se eleva como una
 * parábola, más alto cuanto más lejos. La usan el motor del muro
 * (`engine.ts`) y el laboratorio, para que lo que se midió en la 9.1 sea lo
 * mismo que ve el analista.
 *
 * No hace: no dibuja; son cálculos puros.
 */
const DEGREES = Math.PI / 180;
const EARTH_RADIUS_M = 6_371_008.8;
// Altura del arco: una fracción de su largo, con piso (que un arco dentro de
// Polanco se vea levantado) y techo (que CDMX–Cancún no salga del cuadro).
export const ARC_HEIGHT_SHARE = 0.22;
export const ARC_MIN_HEIGHT_M = 1_500;
export const ARC_MAX_HEIGHT_M = 700_000;

type Vec3 = [number, number, number];

function toVector(lng: number, lat: number): Vec3 {
  const phi = lat * DEGREES;
  const lambda = lng * DEGREES;
  return [Math.cos(phi) * Math.cos(lambda), Math.cos(phi) * Math.sin(lambda), Math.sin(phi)];
}

/** Distancia sobre la Tierra en metros (gran círculo). */
export function greatCircleMeters(a: [number, number], b: [number, number]): number {
  const [ax, ay, az] = toVector(a[0], a[1]);
  const [bx, by, bz] = toVector(b[0], b[1]);
  const dot = Math.min(1, Math.max(-1, ax * bx + ay * by + az * bz));
  return Math.acos(dot) * EARTH_RADIUS_M;
}

// Circunferencia con el radio de MapLibre (`earthRadius`), para que la altura
// en el plano coincida con `MercatorCoordinate.meterInMercatorCoordinateUnits`.
const EARTH_CIRCUMFERENCE_M = 2 * Math.PI * EARTH_RADIUS_M;

/**
 * Convierte metros de altura a unidades del plano Mercator de MapLibre.
 *
 * Arriba de zoom ~12 MapLibre dibuja el globo como plano, y ahí la altura de
 * una capa propia va en unidades Mercator (1 = el ancho del mundo), no en
 * metros. Mercator estira con la latitud, así que un metro vale más cerca de
 * los polos. Es la misma cuenta que `meterInMercatorCoordinateUnits`.
 *
 * @param lat Latitud del punto, en grados.
 * @param meters Altura en metros.
 * @returns La altura en unidades Mercator.
 *
 * @example
 * metersInMercatorUnits(60, 1) // 2 / 40,030,229: a 60° un metro vale el doble
 */
export function metersInMercatorUnits(lat: number, meters: number): number {
  return meters / (EARTH_CIRCUMFERENCE_M * Math.cos(lat * DEGREES));
}

/** Altura máxima del arco entre dos puntos, en metros. */
export function arcHeightMeters(distanceMeters: number): number {
  return Math.min(ARC_MAX_HEIGHT_M, Math.max(ARC_MIN_HEIGHT_M, distanceMeters * ARC_HEIGHT_SHARE));
}

/**
 * Puntos del arco de luz entre dos lugares: sigue el gran círculo y se eleva
 * como una parábola (seno), más alto cuanto más lejos.
 *
 * @param a Origen [lng, lat].
 * @param b Destino [lng, lat].
 * @param samples Puntos del arco (incluye los extremos); más puntos, arco más suave.
 * @returns `[lng, lat, alturaEnMetros]` de cada punto.
 */
export function arcPath(
  a: [number, number],
  b: [number, number],
  samples: number,
): [number, number, number][] {
  const va = toVector(a[0], a[1]);
  const vb = toVector(b[0], b[1]);
  const dot = Math.min(1, Math.max(-1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2]));
  const omega = Math.acos(dot);
  const height = arcHeightMeters(omega * EARTH_RADIUS_M);
  const points: [number, number, number][] = [];
  const count = Math.max(2, samples);
  for (let i = 0; i < count; i += 1) {
    const t = i / (count - 1);
    // Interpolación esférica (slerp); si los puntos casi coinciden, lineal.
    const [wa, wb] =
      omega < 1e-9
        ? [1 - t, t]
        : [Math.sin((1 - t) * omega) / Math.sin(omega), Math.sin(t * omega) / Math.sin(omega)];
    const x = wa * va[0] + wb * vb[0];
    const y = wa * va[1] + wb * vb[1];
    const z = wa * va[2] + wb * vb[2];
    const lat = Math.atan2(z, Math.hypot(x, y)) / DEGREES;
    const lng = Math.atan2(y, x) / DEGREES;
    points.push([lng, lat, height * Math.sin(Math.PI * t)]);
  }
  return points;
}
