/**
 * Cálculo de la mini gráfica de línea (27/10/2026, components/ui/Sparkline).
 *
 * No hace: no dibuja; solo da los puntos dentro del recuadro.
 */

/**
 * Puntos de la línea dentro del recuadro.
 *
 * @example sparklinePoints([0, 5, 10], 100, 20) // [[3, 17], [50, 10], [97, 3]]
 */
export function sparklinePoints(
  values: readonly number[],
  width: number,
  height: number,
): [number, number][] {
  if (values.length === 0) return [];
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  // Margen para que el trazo y el punto final (radio 2.5) no se corten.
  const pad = 3;
  const usable = height - 2 * pad;
  const step = values.length > 1 ? (width - 2 * pad) / (values.length - 1) : 0;
  return values.map((value, index) => [
    Math.round((pad + index * step) * 10) / 10,
    Math.round((pad + usable - ((value - min) / span) * usable) * 10) / 10,
  ]);
}
