import { describe, expect, it } from 'vitest';

import {
  nodePadding,
  orbitBearing,
  WALL_PANEL_WIDTH_PX,
  wallCaseFromHash,
  wallHash,
} from './orbit';

describe('cámara del muro', () => {
  it('orbita despacio y se queda en el rango de MapLibre', () => {
    expect(orbitBearing(0, 0)).toBe(0);
    expect(orbitBearing(10, 2500)).toBe(20);
    expect(orbitBearing(170, 5000)).toBe(-170);
    expect(orbitBearing(-170, 90_000)).toBe(-170); // una vuelta completa
  });

  it('deja libre el panel de la derecha solo en pantallas anchas', () => {
    expect(nodePadding(1600).right).toBeGreaterThan(WALL_PANEL_WIDTH_PX);
    expect(nodePadding(400).right).toBe(0);
  });
});

describe('URL del muro', () => {
  it('lee y arma el caso de la URL', () => {
    expect(wallCaseFromHash('#/explorar?caso=2d6f')).toBe('2d6f');
    expect(wallCaseFromHash('#/explorar')).toBeNull();
    expect(wallCaseFromHash('#/casos?caso=2d6f')).toBeNull();
    expect(wallHash('2d6f')).toBe('#/explorar?caso=2d6f');
    expect(wallHash(null)).toBe('#/explorar');
  });
});
