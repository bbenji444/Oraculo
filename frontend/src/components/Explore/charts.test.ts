import { describe, expect, it } from 'vitest';

import { barHeights, donutSegments } from './charts';

describe('dona', () => {
  it('reparte la vuelta según los valores', () => {
    const [a, b] = donutSegments([3, 1]);

    expect(a?.start).toBe(0);
    expect(a?.end).toBeCloseTo((3 / 4) * 2 * Math.PI);
    expect(b?.end).toBeCloseTo(2 * Math.PI);
    expect(a?.path.startsWith('M ')).toBe(true);
    expect(a?.path.endsWith('Z')).toBe(true);
  });

  it('una sola rebanada dibuja el anillo completo y sin datos no rompe', () => {
    const [only] = donutSegments([5]);

    expect(only?.path.match(/A /g)).toHaveLength(4);
    expect(donutSegments([0, 0]).map((s) => s.end)).toEqual([0, 0]);
  });
});

describe('barras', () => {
  it('proporcionales a la más alta', () => {
    expect(barHeights([7, 3, 1], 70)).toEqual([70, 30, 10]);
    expect(barHeights([], 70)).toEqual([]);
    expect(barHeights([0], 70)).toEqual([0]);
  });
});
