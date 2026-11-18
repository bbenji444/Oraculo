/** Cálculos de la constelación del fondo, con los valores de Oráculo core. */
import { describe, expect, it } from 'vitest';

import {
  CONNECTION_DISTANCE,
  HALO_COUNT,
  HALO_PULSE_PX,
  haloRadius,
  linksBetween,
  makeHalos,
  makeParticles,
  PARTICLE_COUNT,
  type Particle,
  stepHalo,
  stepParticle,
} from './constellation';

/** Aleatorios fijos que recorren 0, 0.25, 0.5, 0.75, … para pruebas repetibles. */
function sequence(): () => number {
  let i = 0;
  return () => (i++ % 4) / 4;
}

function particle(x: number, y: number): Particle {
  return { x, y, vx: 0, vy: 0, size: 1 };
}

describe('makeParticles', () => {
  it('reparte 60 puntos dentro del área, de 1 a 3 px y despacio', () => {
    const particles = makeParticles(800, 600, sequence());
    expect(particles).toHaveLength(PARTICLE_COUNT);
    for (const p of particles) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(800);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(600);
      expect(p.size).toBeGreaterThanOrEqual(1);
      expect(p.size).toBeLessThanOrEqual(3);
      expect(Math.abs(p.vx)).toBeLessThanOrEqual(0.15);
      expect(Math.abs(p.vy)).toBeLessThanOrEqual(0.15);
    }
  });
});

describe('makeHalos', () => {
  it('crea 5 halos grandes, de 50 a 150 px', () => {
    const halos = makeHalos(800, 600, sequence());
    expect(halos).toHaveLength(HALO_COUNT);
    for (const h of halos) {
      expect(h.size).toBeGreaterThanOrEqual(50);
      expect(h.size).toBeLessThanOrEqual(150);
    }
  });
});

describe('stepParticle', () => {
  it('avanza según los cuadros que pasaron', () => {
    const p = { x: 10, y: 10, vx: 0.1, vy: -0.1, size: 1 };
    stepParticle(p, 100, 100, 2);
    expect(p.x).toBeCloseTo(10.2);
    expect(p.y).toBeCloseTo(9.8);
  });

  it('rebota al pasar una orilla', () => {
    const p = { x: 99.95, y: 50, vx: 0.1, vy: 0, size: 1 };
    stepParticle(p, 100, 100, 1);
    expect(p.vx).toBeCloseTo(-0.1);
  });
});

describe('stepHalo', () => {
  it('al salir por la derecha entra por la izquierda', () => {
    const h = { x: 160, y: 50, vx: 0.05, vy: 0, size: 50, pulse: 0 };
    stepHalo(h, 100, 100, 1);
    expect(h.x).toBe(-50);
  });

  it('late ±20 px alrededor de su tamaño', () => {
    const h = { x: 0, y: 0, vx: 0, vy: 0, size: 80, pulse: Math.PI / 2 };
    expect(haloRadius(h)).toBeCloseTo(80 + HALO_PULSE_PX);
    h.pulse = -Math.PI / 2;
    expect(haloRadius(h)).toBeCloseTo(80 - HALO_PULSE_PX);
  });
});

describe('linksBetween', () => {
  it('une solo a los cercanos, más delgado mientras más lejos', () => {
    const a = particle(0, 0);
    const b = particle(75, 0);
    const c = particle(0, CONNECTION_DISTANCE + 1);
    const links = linksBetween([a, b, c]);
    expect(links).toHaveLength(1);
    const [link] = links;
    expect(link).toMatchObject({ from: a, to: b });
    expect(link?.width).toBeCloseTo(0.5);
  });
});
