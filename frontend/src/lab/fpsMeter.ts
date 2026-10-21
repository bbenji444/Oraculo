/**
 * Medidor de cuadros por segundo del laboratorio del muro (ADR-0102).
 *
 * Mide el tiempo entre cuadros con `requestAnimationFrame`, el mismo método de
 * las mediciones de vuelos del 20/10/2026, y lo resume en tres números:
 * - **fps promedio** (1000 / tiempo medio de cuadro);
 * - **p95**: el 95 % de los cuadros tardó esto o menos (los tirones se ven aquí);
 * - **cuadros lentos**: % de cuadros de más de 16.7 ms (no llegaron a 60 fps).
 *
 * No hace: no mueve la cámara ni dibuja nada; solo cuenta.
 */

/** Un cuadro a 60 fps dura 1000 / 60 ms. */
export const FRAME_BUDGET_MS = 1000 / 60;
// Un cuadro de 16.9 ms en una pantalla de 60 Hz no es un tirón visible:
// pequeño margen para el redondeo de los tiempos del navegador.
const SLOW_MARGIN_MS = 0.5;

export interface FrameStats {
  frames: number;
  fps: number;
  p95Ms: number;
  slowShare: number;
}

/**
 * Resume los tiempos entre cuadros.
 *
 * @param intervalsMs Milisegundos entre cuadros consecutivos.
 * @returns Promedio de fps, p95 en ms y fracción de cuadros lentos (0..1).
 * @example frameStats([16.6, 16.7, 33.4]) // { fps: 45, p95Ms: 33.4, slowShare: 0.33, frames: 3 }
 */
export function frameStats(intervalsMs: readonly number[]): FrameStats {
  const valid = intervalsMs.filter((ms) => Number.isFinite(ms) && ms > 0);
  if (valid.length === 0) return { frames: 0, fps: 0, p95Ms: 0, slowShare: 0 };
  const sorted = [...valid].sort((a, b) => a - b);
  const mean = sorted.reduce((sum, ms) => sum + ms, 0) / sorted.length;
  const p95 = sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1)] ?? 0;
  const slow = sorted.filter((ms) => ms > FRAME_BUDGET_MS + SLOW_MARGIN_MS).length;
  return {
    frames: sorted.length,
    fps: Math.round((1000 / mean) * 10) / 10,
    p95Ms: Math.round(p95 * 10) / 10,
    slowShare: Math.round((slow / sorted.length) * 1000) / 1000,
  };
}

/**
 * Junta los tiempos entre cuadros durante `durationMs`.
 *
 * @param durationMs Cuánto medir.
 * @returns Milisegundos entre cuadros (el primero se descarta: no tiene anterior).
 */
export function recordFrames(durationMs: number): Promise<number[]> {
  return new Promise((resolve) => {
    const intervals: number[] = [];
    const start = performance.now();
    let last = start;
    const tick = (now: number) => {
      if (now !== start) intervals.push(now - last);
      last = now;
      if (now - start < durationMs) requestAnimationFrame(tick);
      else resolve(intervals.slice(1));
    };
    requestAnimationFrame(tick);
  });
}

/**
 * Junta varias corridas del mismo paso: fps y cuadros lentos promedio, y el
 * peor p95 (un solo tirón fuerte basta para que se note).
 *
 * @param runs Estadísticas de cada corrida.
 * @returns El resumen, o `null` si no hay corridas.
 */
export function summarizeRuns(runs: readonly FrameStats[]): FrameStats | null {
  if (runs.length === 0) return null;
  const mean = (pick: (s: FrameStats) => number) =>
    runs.reduce((sum, s) => sum + pick(s), 0) / runs.length;
  return {
    frames: Math.round(mean((s) => s.frames)),
    fps: Math.round(mean((s) => s.fps) * 10) / 10,
    p95Ms: Math.max(...runs.map((s) => s.p95Ms)),
    slowShare: Math.round(mean((s) => s.slowShare) * 1000) / 1000,
  };
}
