import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  EARTH_AXIAL_TILT_DEGREES,
  GLOBE_BEARING,
  GLOBE_TILT_DEGREES,
  MAX_SPIN_ZOOM,
  prefersReducedMotion,
  REGION_BEARING,
  SLOW_SPIN_ZOOM,
  spinDegrees,
  SPIN_STEP_MS,
} from './spin';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('spinDegrees', () => {
  it('a zoom de globo avanza 4° por segundo: una vuelta en 90 s', () => {
    expect(spinDegrees(1.8)).toBeCloseTo(4);
    expect(spinDegrees(1.8, SPIN_STEP_MS / 2)).toBeCloseTo(2);
  });

  it('se frena poco a poco al acercarse y se detiene en el zoom máximo', () => {
    const middle = (SLOW_SPIN_ZOOM + MAX_SPIN_ZOOM) / 2;

    expect(spinDegrees(SLOW_SPIN_ZOOM)).toBeCloseTo(4);
    expect(spinDegrees(middle)).toBeCloseTo(2);
    expect(spinDegrees(MAX_SPIN_ZOOM)).toBe(0);
    expect(spinDegrees(8)).toBe(0);
  });
});

describe('prefersReducedMotion', () => {
  it('respeta la preferencia del sistema', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: true })),
    );
    expect(prefersReducedMotion()).toBe(true);

    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false })),
    );
    expect(prefersReducedMotion()).toBe(false);
  });
});

describe('inclinación del globo', () => {
  it('se inclina menos que el eje real y se endereza al ver una región', () => {
    expect(GLOBE_TILT_DEGREES).toBeGreaterThan(0);
    expect(GLOBE_TILT_DEGREES).toBeLessThan(EARTH_AXIAL_TILT_DEGREES);
    // Negativo: el polo norte se inclina hacia la derecha.
    expect(GLOBE_BEARING).toBe(-GLOBE_TILT_DEGREES);
    expect(REGION_BEARING).toBe(0);
  });
});
