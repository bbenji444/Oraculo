import { describe, expect, it } from 'vitest';

import {
  durationFactor,
  easeInOutCubic,
  easeOutCubic,
  easeOutQuint,
  introSpin,
  FLY_MAX_MS,
  FLY_MIN_MS,
  FLY_ARTICLE_FACTOR,
  flyDurationMs,
  flyPitch,
  greatCircleDegrees,
  pulsePhase,
  spinFactor,
  spinRamp,
  SPIN_RAMP_MS,
  staggerDelayMs,
  STAGGER_MAX_MS,
} from './motion';

const MEXICO = { lng: -102, lat: 23, zoom: 2 };
const JALISCO = { lng: -103.4, lat: 20.6, zoom: 7 };

describe('distancia en la esfera', () => {
  it('mide grados de arco', () => {
    expect(greatCircleDegrees({ lng: 0, lat: 0 }, { lng: 90, lat: 0 })).toBeCloseTo(90);
    expect(greatCircleDegrees({ lng: 0, lat: 90 }, { lng: 120, lat: 90 })).toBeCloseTo(0);
    expect(greatCircleDegrees({ lng: -179, lat: 0 }, { lng: 179, lat: 0 })).toBeCloseTo(2);
  });
});

describe('duración de los vuelos', () => {
  it('crece con la distancia y el zoom, dentro de sus límites', () => {
    const near = flyDurationMs(MEXICO, JALISCO, 'region', 'normal');
    const far = flyDurationMs(MEXICO, { lng: 2, lat: 41, zoom: 7 }, 'region', 'normal');

    expect(near).toBe(2675);
    expect(far).toBeGreaterThan(near);
    expect(flyDurationMs(MEXICO, MEXICO, 'region', 'normal')).toBe(FLY_MIN_MS);
    expect(flyDurationMs(MEXICO, { lng: 120, lat: -30, zoom: 14 }, 'region', 'normal')).toBe(
      FLY_MAX_MS,
    );
  });

  it('subir de nivel es más rápido y la velocidad elegida escala todo', () => {
    const normal = flyDurationMs(MEXICO, JALISCO, 'region', 'normal');

    // Se redondea al final, así que puede diferir en 1 ms del cálculo aproximado.
    expect(flyDurationMs(JALISCO, MEXICO, 'up', 'normal')).toBeCloseTo(normal * 0.6, -1);
    expect(flyDurationMs(MEXICO, JALISCO, 'region', 'slow')).toBeCloseTo(normal * 1.6, -1);
    expect(flyDurationMs(MEXICO, JALISCO, 'region', 'fast')).toBeCloseTo(normal * 0.6, -1);
    expect(flyDurationMs(MEXICO, JALISCO, 'region', 'off')).toBe(0);
  });

  it('inclina más la cámara cuanto más cerca', () => {
    expect(flyPitch('country')).toBe(0);
    expect(flyPitch('state')).toBeLessThan(flyPitch('municipality'));
    expect(flyPitch('municipality')).toBeLessThan(flyPitch('locality'));
  });
});

describe('curvas y rotación', () => {
  it('las curvas van de 0 a 1 sin pasarse', () => {
    for (const ease of [easeInOutCubic, easeOutQuint]) {
      expect(ease(0)).toBe(0);
      expect(ease(1)).toBe(1);
      expect(ease(0.5)).toBeGreaterThan(0);
      expect(ease(0.5)).toBeLessThan(1);
    }
    // La de entrada frena al final: a la mitad ya recorrió casi todo.
    expect(easeOutQuint(0.5)).toBeGreaterThan(0.9);
  });

  it('la entrada llega con la velocidad del giro, sin quedarse quieta', () => {
    const endSlope = 0.13;
    const step = 1e-4;

    expect(introSpin(0, endSlope)).toBe(0);
    expect(introSpin(1, endSlope)).toBeCloseTo(1);
    // Al final va justo a la velocidad del giro (no a cero, como la quíntica).
    const endSpeed = (introSpin(1, endSlope) - introSpin(1 - step, endSlope)) / step;
    expect(endSpeed).toBeCloseTo(endSlope, 3);
    // Frena parejo: siempre avanza y nunca se pasa.
    for (let t = 0.05; t <= 1; t += 0.05) {
      expect(introSpin(t, endSlope)).toBeGreaterThan(introSpin(t - 0.05, endSlope));
      expect(introSpin(t, endSlope)).toBeLessThanOrEqual(1 + 1e-9);
    }
    expect(easeOutCubic(1)).toBe(1);
  });

  it('la rotación arranca acelerando, sin saltos', () => {
    expect(spinRamp(0)).toBe(0);
    expect(spinRamp(SPIN_RAMP_MS / 4)).toBeLessThan(spinRamp(SPIN_RAMP_MS / 2));
    expect(spinRamp(SPIN_RAMP_MS)).toBe(1);
    expect(spinRamp(SPIN_RAMP_MS * 3)).toBe(1);
  });

  it('cada velocidad tiene su factor', () => {
    expect([durationFactor('slow'), durationFactor('fast'), durationFactor('off')]).toEqual([
      1.6, 0.6, 0,
    ]);
    expect([
      spinFactor('slow'),
      spinFactor('normal'),
      spinFactor('fast'),
      spinFactor('off'),
    ]).toEqual([0.6, 1, 1.6, 0]);
  });
});

describe('aparición de los resultados', () => {
  it('cascada de 30 ms que nunca pasa de 1.5 s', () => {
    expect(staggerDelayMs(0, 10, 'normal')).toBe(0);
    expect(staggerDelayMs(3, 10, 'normal')).toBe(90);
    expect(staggerDelayMs(149, 150, 'normal')).toBeLessThanOrEqual(STAGGER_MAX_MS);
    expect(staggerDelayMs(5, 10, 'off')).toBe(0);
    expect(staggerDelayMs(0, 1, 'normal')).toBe(0);
  });

  it('el latido se repite', () => {
    expect(pulsePhase(0)).toBe(0);
    expect(pulsePhase(700)).toBeCloseTo(0.5);
    expect(pulsePhase(1400)).toBe(0);
  });
});

describe('vuelo a una nota', () => {
  it('es más ágil que el vuelo a una región con el mismo recorrido', () => {
    const from = { lng: -102, lat: 23, zoom: 2 };
    const to = { lng: -98.2, lat: 19.3, zoom: 11.5 };
    const region = flyDurationMs(from, to, 'region', 'normal');
    expect(flyDurationMs(from, to, 'article', 'normal')).toBe(
      Math.round(region * FLY_ARTICLE_FACTOR),
    );
  });
});
