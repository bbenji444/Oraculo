import { describe, expect, it } from 'vitest';

import {
  angularDistance,
  contactBirths,
  contactMesh,
  contactPoints,
  destination,
  domeMesh,
  domeShape,
  MAX_CONTACTS,
} from './dome';

// Números por vértice: posición (2), alturas (2), u, t, tipo, nacimiento y semilla.
const STRIDE = 9;

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
    // 2 mallas de (4 + 1) × (8 + 1) vértices.
    expect(floats.length).toBe(2 * 5 * 9 * STRIDE);
    expect(indices.length).toBe(2 * 4 * 8 * 6);
    // El primer vértice de la cúpula (después del piso) es la cima: altura máxima.
    const domeStart = 5 * 9 * STRIDE;
    expect(floats[domeStart + 2]).toBeCloseTo(shape.heightM, 0);
    expect(floats[domeStart + 6]).toBe(0);
    // El piso va pegado al terreno.
    expect(floats[2]).toBe(0);
    expect(floats[6]).toBe(1);
  });

  it('los contactos caen dentro de la cúpula y no brincan al llegar más', () => {
    const shape = domeShape(CHIAPAS);
    const points = contactPoints(shape, 10);

    expect(points).toHaveLength(10);
    // Los primeros 5 están donde estaban cuando había 5.
    expect(points.slice(0, 5)).toEqual(contactPoints(shape, 5));
    for (const point of points) {
      expect(angularDistance(point, shape.center)).toBeLessThan(
        ((shape.radiusM * 0.8) / 6_371_008.8) * (180 / Math.PI) + 1e-6,
      );
    }
  });

  it('las columnas no atraviesan la cúpula y la onda va pegada al piso', () => {
    const shape = domeShape(CHIAPAS);
    const { floats, indices } = contactMesh(shape, [5, 6]);
    let tallest = 0;
    for (let v = 0; v < floats.length; v += STRIDE) {
      const kind = floats[v + 6];
      const meters = floats[v + 2] ?? 0;
      if (kind === 2) tallest = Math.max(tallest, meters);
      if (kind === 3) expect(meters).toBe(0);
    }

    expect(indices.length).toBeGreaterThan(0);
    expect(tallest).toBeGreaterThan(0);
    expect(tallest).toBeLessThan(shape.heightM);
    // Cada vértice lleva el segundo en que se encendió su contacto.
    expect(floats[7]).toBe(5);
    expect(floats[floats.length - STRIDE + 7]).toBe(6);
    expect(contactMesh(shape, []).indices).toHaveLength(0);
  });

  it('los contactos nuevos se encienden uno tras otro y los viejos no cambian', () => {
    expect(contactBirths([], 2, 10)).toEqual([10, 10.18]);
    const later = contactBirths([10, 10.18], 4, 20);
    expect(later.slice(0, 2)).toEqual([10, 10.18]);
    expect(later[2]).toBeCloseTo(20.18);
    expect(later[3]).toBeCloseTo(20.36);
    // Más notas que columnas: se queda en el tope.
    expect(contactBirths([], 500, 0)).toHaveLength(MAX_CONTACTS);
  });
});
