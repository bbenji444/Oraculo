import { describe, expect, it } from 'vitest';

import {
  ARC_MAX_HEIGHT_M,
  ARC_MIN_HEIGHT_M,
  arcHeightMeters,
  arcPath,
  DEMO_CASE,
  greatCircleMeters,
  nodesById,
  syntheticCase,
} from './labCase';

describe('casos de prueba del muro', () => {
  it('el caso de Polanco no trae nombres reales ni "culpable"', () => {
    const labels = DEMO_CASE.nodes.map((n) => n.label).join(' ');

    expect(labels).not.toMatch(/Micky|Eduardo|Mora|Ederly/i);
    expect(DEMO_CASE.nodes.every((n) => n.legal === null || n.kind === 'person')).toBe(true);
    // Todo vínculo une dos nodos que existen.
    const byId = nodesById(DEMO_CASE);
    expect(DEMO_CASE.links.every((l) => byId.has(l.from) && byId.has(l.to))).toBe(true);
  });

  it('un caso sintético es repetible, del tamaño pedido y sin vínculos a sí mismo', () => {
    const a = syntheticCase(150);
    const b = syntheticCase(150);

    expect(a).toEqual(b);
    expect(a.nodes).toHaveLength(150);
    expect(a.links.length).toBeGreaterThan(150);
    expect(a.links.every((l) => l.from !== l.to)).toBe(true);
    // Todos en México (recuadro amplio).
    expect(a.nodes.every((n) => n.lng > -119 && n.lng < -86 && n.lat > 14 && n.lat < 33)).toBe(
      true,
    );
  });
});

describe('geometría de los arcos', () => {
  it('CDMX–Cancún mide unos 1,295 km', () => {
    expect(greatCircleMeters([-99.13, 19.43], [-86.85, 21.16]) / 1000).toBeCloseTo(1295, -1);
  });

  it('la altura crece con la distancia, con piso y techo', () => {
    expect(arcHeightMeters(100)).toBe(ARC_MIN_HEIGHT_M);
    expect(arcHeightMeters(1_000_000)).toBe(220_000);
    expect(arcHeightMeters(20_000_000)).toBe(ARC_MAX_HEIGHT_M);
  });

  it('el arco empieza y termina en el suelo, y sube a la mitad', () => {
    const path = arcPath([-99.13, 19.43], [-86.85, 21.16], 33);
    const [first, middle, last] = [path[0], path[16], path[32]];

    expect(path).toHaveLength(33);
    expect(first?.[2]).toBeCloseTo(0);
    expect(last?.[2]).toBeCloseTo(0);
    expect(first?.[0]).toBeCloseTo(-99.13);
    expect(last?.[1]).toBeCloseTo(21.16);
    expect(middle?.[2]).toBeCloseTo(
      arcHeightMeters(greatCircleMeters([-99.13, 19.43], [-86.85, 21.16])),
    );
  });

  it('dos puntos iguales no rompen el cálculo', () => {
    const path = arcPath([-99.2, 19.43], [-99.2, 19.43], 5);

    expect(path.every(([lng, lat]) => Number.isFinite(lng) && Number.isFinite(lat))).toBe(true);
  });
});
