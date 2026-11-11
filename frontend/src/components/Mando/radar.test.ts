import { describe, expect, it } from 'vitest';

import { blips, coordinatesLabel, MIN_RADIUS_PX, radarGeometry } from './radar';

// Proyección de juguete: 10 px por grado, con el origen en (100, 100).
const project = ([lng, lat]: [number, number]) => ({ x: 100 + lng * 10, y: 100 - lat * 10 });
const VIEW = { width: 1200, height: 800 };

describe('radar sobre la zona buscada (11/11/2026)', () => {
  it('se centra en la región y la abarca', () => {
    // Una región de 20° × 10°: 200 px × 100 px en pantalla.
    const geometry = radarGeometry(project, [0, 0, 20, 10], VIEW);

    expect([geometry.cx, geometry.cy]).toEqual([200, 50]);
    expect(geometry.radius).toBe(115); // la mitad del lado mayor, con aire
    expect(geometry.box).toEqual({ left: 100, top: 0, width: 200, height: 100 });
  });

  it('una región pequeña tiene un radar que se lee y una enorme no tapa todo', () => {
    expect(radarGeometry(project, [0, 0, 0.5, 0.5], VIEW).radius).toBe(MIN_RADIUS_PX);
    expect(radarGeometry(project, [0, 0, 400, 300], VIEW).radius).toBe(336); // 42 % de 800
  });

  it('los ecos caen dentro del radar y no cambian de lugar', () => {
    const many = blips(12);

    expect(many).toHaveLength(12);
    for (const blip of many) {
      expect(Math.hypot(blip.x - 50, blip.y - 50)).toBeLessThanOrEqual(42.5);
    }
    expect(blips(12)).toEqual(many);
    expect(blips(3)[1]?.delay).toBe(0.45);
    expect(blips(0)).toEqual([]);
  });

  it('dice las coordenadas del centro', () => {
    expect(coordinatesLabel([-117.1, 14.5, -86.7, 32.7])).toBe('23.60° N · 101.90° O');
  });
});
