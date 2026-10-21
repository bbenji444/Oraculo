import { describe, expect, it } from 'vitest';

import { frameStats, summarizeRuns } from './fpsMeter';

describe('medidor de fps', () => {
  it('60 fps parejos: sin cuadros lentos', () => {
    const stats = frameStats(Array.from({ length: 120 }, () => 1000 / 60));

    expect(stats).toEqual({ frames: 120, fps: 60, p95Ms: 16.7, slowShare: 0 });
  });

  it('los tirones aparecen en el p95 y en los cuadros lentos aunque el promedio sea bueno', () => {
    // 95 cuadros a 60 fps y 5 tirones de 50 ms.
    const stats = frameStats([...Array.from({ length: 95 }, () => 16.6), ...[50, 50, 50, 50, 50]]);

    expect(stats.slowShare).toBe(0.05);
    expect(stats.p95Ms).toBe(16.6);
    expect(stats.fps).toBeLessThan(55);
  });

  it('sin cuadros válidos no divide entre cero', () => {
    expect(frameStats([])).toEqual({ frames: 0, fps: 0, p95Ms: 0, slowShare: 0 });
    expect(frameStats([Number.NaN, -1]).frames).toBe(0);
  });
});

describe('resumen de corridas', () => {
  it('promedia fps y lentos, y se queda con el peor p95', () => {
    const summary = summarizeRuns([
      { frames: 300, fps: 60, p95Ms: 16.7, slowShare: 0 },
      { frames: 280, fps: 56, p95Ms: 25, slowShare: 0.04 },
    ]);

    expect(summary).toEqual({ frames: 290, fps: 58, p95Ms: 25, slowShare: 0.02 });
    expect(summarizeRuns([])).toBeNull();
  });
});
