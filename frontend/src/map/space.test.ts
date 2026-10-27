import { describe, expect, it } from 'vitest';

import {
  makeStars,
  seededRandom,
  starCameraRotation,
  starTextureFor,
  STAR_COUNT,
  STAR_MAX_SIZE,
  STAR_MIN_SIZE,
} from './space';

describe('fondo de universo', () => {
  it('la cámara de las estrellas gira con la del mapa', () => {
    const still = starCameraRotation({ lng: 0, lat: 0, zoom: 2, bearing: 0, pitch: 0 });
    const turned = starCameraRotation({ lng: -90, lat: 20, zoom: 2, bearing: -15, pitch: 30 });

    expect(still).toEqual({ x: 0, y: 0, z: 0 });
    expect(turned.y).toBeCloseTo(-Math.PI / 2);
    expect(turned.x).toBeCloseTo((10 * Math.PI) / 180);
    expect(turned.z).toBeCloseTo((-15 * Math.PI) / 180);
  });

  it('usa 8K con tarjeta que la acepte y pantalla de 1,600 px o más', () => {
    expect(starTextureFor(16384, 3840)).toBe('starmap_8k.jpg');
    // Laptop de 1366 px al 125 %: ya carga la 8K (con la 4K se veía pixeleado).
    expect(starTextureFor(16384, 1707)).toBe('starmap_8k.jpg');
    expect(starTextureFor(16384, 1280)).toBe('starmap_4k.jpg');
    expect(starTextureFor(4096, 3840)).toBe('starmap_4k.jpg');
  });

  it('las estrellas son siempre las mismas y están sobre la esfera', () => {
    const stars = makeStars();
    const again = makeStars();

    expect(stars).toHaveLength(STAR_COUNT);
    expect(again[123]).toEqual(stars[123]);
    for (const star of stars.slice(0, 200)) {
      expect(Math.hypot(star.x, star.y, star.z)).toBeCloseTo(1);
      expect(star.size).toBeGreaterThanOrEqual(STAR_MIN_SIZE);
      expect(star.size).toBeLessThanOrEqual(STAR_MAX_SIZE);
    }
    // La mayoría son pequeñas: el promedio queda abajo de la mitad del rango.
    const mean = stars.reduce((sum, s) => sum + s.size, 0) / stars.length;
    expect(mean).toBeLessThan((STAR_MIN_SIZE + STAR_MAX_SIZE) / 2);
  });

  it('el generador con semilla repite la serie', () => {
    const a = seededRandom(7);
    const b = seededRandom(7);

    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });
});
