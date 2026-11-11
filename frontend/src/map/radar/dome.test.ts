import { describe, expect, it } from 'vitest';

import { angularDistance, blipPoints, destination, domeMesh, domeShape } from './dome';

const MEXICO: [number, number, number, number] = [-117.1, 14.5, -86.7, 32.7];
const CHIAPAS: [number, number, number, number] = [-94.1, 14.5, -90.4, 17.99];

describe('cúpula 3D del radar (11/11/2026)', () => {
  it('se centra en la región y crece con ella, sin tapar el planeta', () => {
    const chiapas = domeShape(CHIAPAS);
    const mexico = domeShape(MEXICO);

    expect(chiapas.center[0]).toBeCloseTo(-92.25);
    expect(chiapas.center[1]).toBeCloseTo(16.245);
    expect(chiapas.radiusM).toBeGreaterThan(180_000);
    expect(chiapas.radiusM).toBeLessThan(260_000);
    expect(mexico.radiusM).toBe(1_600_000); // tope
    expect(chiapas.heightM).toBeCloseTo(chiapas.radiusM * 0.42);
    // Un municipio diminuto sigue viéndose.
    expect(domeShape([-99.1, 19.4, -99.09, 19.41]).radiusM).toBe(8_000);
  });

  it('sabe si la zona está lejos de lo que se ve', () => {
    expect(angularDistance([-99, 19], [-99, 19])).toBe(0);
    expect(angularDistance([0, 0], [90, 0])).toBeCloseTo(90);
    expect(angularDistance([-99, 19], [10, 30])).toBeGreaterThan(90);
  });

  it('un punto a 111 km al norte sube un grado de latitud', () => {
    const [lng, lat] = destination([-99, 19], 111_195, 0);

    expect(lng).toBeCloseTo(-99, 6);
    expect(lat).toBeCloseTo(20, 2);
  });

  it('la malla trae la cúpula y el piso, con su cima arriba', () => {
    const shape = domeShape(CHIAPAS);
    const { floats, indices } = domeMesh(shape, 4, 8);
    // 2 mallas de (4 + 1) × (8 + 1) vértices, 7 números cada uno.
    expect(floats.length).toBe(2 * 5 * 9 * 7);
    expect(indices.length).toBe(2 * 4 * 8 * 6);
    // El primer vértice de la cúpula (después del piso) es la cima: altura máxima.
    const domeStart = 5 * 9 * 7;
    expect(floats[domeStart + 2]).toBeCloseTo(shape.heightM, 0);
    expect(floats[domeStart + 6]).toBe(0);
    // El piso va pegado al terreno.
    expect(floats[2]).toBe(0);
    expect(floats[6]).toBe(1);
  });

  it('los ecos caen dentro de la cúpula y no cambian de lugar', () => {
    const shape = domeShape(CHIAPAS);
    const points = blipPoints(shape, 10);

    expect(points).toHaveLength(10);
    expect(blipPoints(shape, 10)).toEqual(points);
    for (const [lng, lat] of points) {
      expect(Math.abs(lng - shape.center[0])).toBeLessThan(3);
      expect(Math.abs(lat - shape.center[1])).toBeLessThan(3);
    }
  });
});
