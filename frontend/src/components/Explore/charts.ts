/**
 * Geometría de las gráficas de Explorar (SVG propio, sin librería; ADR-0017).
 *
 * Funciones puras: de conteos a barras y a rebanadas de dona.
 */

/** Una rebanada de la dona, en radianes (0 = arriba, sentido horario). */
export interface DonutSegment {
  start: number;
  end: number;
  /** Trazo SVG del arco (anillo). */
  path: string;
}

const FULL_TURN = 2 * Math.PI;
// Un hueco pequeño entre rebanadas se lee mejor que rebanadas pegadas.
export const DONUT_GAP_RADIANS = 0.03;

function point(radius: number, angle: number, center: number): string {
  // 0 rad arriba: se resta un cuarto de vuelta al ángulo matemático.
  const x = center + radius * Math.cos(angle - Math.PI / 2);
  const y = center + radius * Math.sin(angle - Math.PI / 2);
  return `${x.toFixed(2)} ${y.toFixed(2)}`;
}

/**
 * Rebanadas de una dona para unos valores.
 *
 * @param values Conteos (los ceros no dibujan rebanada).
 * @param outer Radio exterior.
 * @param inner Radio interior.
 * @returns Una rebanada por valor, en el mismo orden.
 */
export function donutSegments(values: readonly number[], outer = 48, inner = 30): DonutSegment[] {
  const total = values.reduce((sum, v) => sum + v, 0);
  const center = outer;
  let angle = 0;
  return values.map((value) => {
    const share = total > 0 ? value / total : 0;
    const start = angle;
    const end = angle + share * FULL_TURN;
    angle = end;
    const single = share >= 1;
    const gap = single || share === 0 ? 0 : DONUT_GAP_RADIANS / 2;
    // Una sola rebanada de vuelta completa: dos medios arcos (SVG no cierra
    // un arco de 360° en un solo trazo).
    const a = start + gap;
    const b = single ? start + Math.PI : end - gap;
    const large = b - a > Math.PI ? 1 : 0;
    const path = single
      ? `M ${point(outer, 0, center)} A ${String(outer)} ${String(outer)} 0 1 1 ${point(outer, Math.PI, center)} A ${String(outer)} ${String(outer)} 0 1 1 ${point(outer, 0, center)} M ${point(inner, 0, center)} A ${String(inner)} ${String(inner)} 0 1 0 ${point(inner, Math.PI, center)} A ${String(inner)} ${String(inner)} 0 1 0 ${point(inner, 0, center)} Z`
      : `M ${point(outer, a, center)} A ${String(outer)} ${String(outer)} 0 ${String(large)} 1 ${point(outer, b, center)} L ${point(inner, b, center)} A ${String(inner)} ${String(inner)} 0 ${String(large)} 0 ${point(inner, a, center)} Z`;
    return { start, end, path };
  });
}

/**
 * Alturas de barras proporcionales al máximo.
 *
 * @param values Conteos.
 * @param height Altura de la barra más alta.
 */
export function barHeights(values: readonly number[], height: number): number[] {
  const max = Math.max(0, ...values);
  return values.map((value) => (max > 0 ? (value / max) * height : 0));
}
