import { describe, expect, it } from 'vitest';

import {
  makeStars,
  seededRandom,
  driftView,
  DRIFT_DEGREES_PER_SECOND,
  skyTiles,
  SPACE_MAX_PIXEL_RATIO,
  spacePixelRatio,
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

  it('usa 8K siempre que la tarjeta la acepte', () => {
    // Sin importar la pantalla: con la 4K el cielo se veía pixeleado (26/10/2026).
    expect(starTextureFor(16384)).toBe('starmap_8k.jpg');
    expect(starTextureFor(8192)).toBe('starmap_8k.jpg');
    expect(starTextureFor(4096)).toBe('starmap_4k.jpg');
  });

  it('el lienzo del fondo sigue la escala de la pantalla, con tope', () => {
    // Pantalla al 125 %: el fondo se dibuja a 1.25, igual que el mapa.
    expect(spacePixelRatio(1.25)).toBe(1.25);
    expect(spacePixelRatio(1)).toBe(1);
    expect(spacePixelRatio(3)).toBe(SPACE_MAX_PIXEL_RATIO);
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

  it('la 8K se parte en 8 piezas de 2048 que cubren toda la esfera', () => {
    const tiles = skyTiles(8192, 4096);

    expect(tiles).toHaveLength(8);
    expect(tiles.every((t) => t.width === 2048 && t.height === 2048)).toBe(true);
    // Sin huecos ni encimadas: suman la foto entera y la esfera entera.
    expect(tiles.reduce((sum, t) => sum + t.width * t.height, 0)).toBe(8192 * 4096);
    expect(tiles.reduce((sum, t) => sum + t.phiLength * t.thetaLength, 0)).toBeCloseTo(
      2 * Math.PI * Math.PI,
    );
    // La primera es la esquina de arriba a la izquierda: norte, longitud 0.
    expect(tiles[0]).toMatchObject({ x: 0, y: 0, phiStart: 0, thetaStart: 0 });
    expect(tiles[7]).toMatchObject({ x: 6144, y: 2048 });
    expect(tiles[7]?.thetaStart).toBeCloseTo(Math.PI / 2);
  });

  it('fuera de Explorar el cielo deriva despacio desde donde estaba', () => {
    const start = driftView(-102, 0);
    const minute = driftView(-102, 60_000);

    // No salta: arranca en la longitud que tenía la cámara.
    expect(start.lng).toBe(-102);
    expect(minute.lng).toBeCloseTo(-102 - DRIFT_DEGREES_PER_SECOND * 60);
    // El vaivén de latitud es suave y no se pasa de los polos.
    for (let t = 0; t < 400_000; t += 20_000) {
      const { lat } = driftView(0, t);
      expect(Math.abs(lat)).toBeLessThan(25);
    }
  });

  it('la 4K queda en 2 piezas', () => {
    expect(skyTiles(4096, 2048)).toHaveLength(2);
  });

  it('el generador con semilla repite la serie', () => {
    const a = seededRandom(7);
    const b = seededRandom(7);

    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });
});
